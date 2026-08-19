"""Termux-friendly Discord multi-tool bot."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot.sqlite3")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("discord-multitool")


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with database() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                due_at TEXT NOT NULL
            )"""
        )


def parse_duration(value: str) -> Optional[timedelta]:
    match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", value.lower())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    keyword = {"s": "seconds", "m": "minutes", "h": "hours",
               "d": "days", "w": "weeks"}[unit]
    return timedelta(**{keyword: amount})


class MultiToolBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        init_database()
        if GUILD_ID.isdigit():
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Commands synced to test guild %s", GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Global commands synced")
        reminder_loop.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")


bot = MultiToolBot()


@bot.tree.command(description="Check the bot's response time.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        f"Pong! `{round(bot.latency * 1000)}ms`", ephemeral=True
    )


@bot.tree.command(description="Show information about this server.")
async def serverinfo(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command only works in a server.", ephemeral=True)
        return
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    embed.add_field(name="Members", value=str(guild.member_count or "unknown"))
    embed.add_field(name="Channels", value=str(len(guild.channels)))
    embed.add_field(name="Owner", value=f"<@{guild.owner_id}>")
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(description="Show information about a member.")
@app_commands.describe(member="Member to inspect; defaults to yourself.")
async def userinfo(interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
    member = member or interaction.user
    embed = discord.Embed(title=str(member), color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User ID", value=str(member.id))
    embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "unknown")
    embed.add_field(name="Created", value=discord.utils.format_dt(member.created_at, "R"))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(description="Create a yes/no reaction poll.")
@app_commands.describe(question="The question people should vote on.")
async def poll(interaction: discord.Interaction, question: str) -> None:
    embed = discord.Embed(title="Poll", description=question, color=discord.Color.gold())
    embed.set_footer(text=f"Created by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    await message.add_reaction("✅")
    await message.add_reaction("❌")


@bot.tree.command(description="Remind you later. Examples: 10m, 2h, 1d.")
@app_commands.describe(delay="Duration using s, m, h, d, or w.", message="What to remind you about.")
async def remind(interaction: discord.Interaction, delay: str, message: str) -> None:
    duration = parse_duration(delay)
    if duration is None or duration.total_seconds() < 1 or duration.days > 30:
        await interaction.response.send_message("Use a duration like `10m`, `2h`, or `1d` (maximum 30 days).", ephemeral=True)
        return
    due = datetime.now(timezone.utc) + duration
    with database() as connection:
        connection.execute(
            "INSERT INTO reminders (channel_id, user_id, message, due_at) VALUES (?, ?, ?, ?)",
            (interaction.channel_id, interaction.user.id, message, due.isoformat()),
        )
    await interaction.response.send_message(f"Reminder set for {discord.utils.format_dt(due, 'R')}.", ephemeral=True)


@bot.tree.command(description="Delete recent messages.")
@app_commands.describe(amount="Number of messages to delete, from 1 to 100.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]) -> None:
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("This command needs a text channel.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)


@bot.tree.command(description="Kick a member from the server.")
@app_commands.describe(member="Member to kick.", reason="Optional reason.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided") -> None:
    await member.kick(reason=f"{interaction.user}: {reason}")
    await interaction.response.send_message(f"👢 Kicked **{member}**. Reason: {reason}")


@bot.tree.command(description="Ban a member from the server.")
@app_commands.describe(member="Member to ban.", reason="Optional reason.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided") -> None:
    await member.ban(reason=f"{interaction.user}: {reason}")
    await interaction.response.send_message(f"🔨 Banned **{member}**. Reason: {reason}")


@bot.tree.command(name="note_add", description="Save a private server note about a member.")
@app_commands.describe(member="Member the note is about.", content="Note content.")
@app_commands.checks.has_permissions(manage_guild=True)
async def note_add(interaction: discord.Interaction, member: discord.Member, content: str) -> None:
    with database() as connection:
        connection.execute(
            "INSERT INTO notes (guild_id, user_id, author_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild_id, member.id, interaction.user.id, content, datetime.now(timezone.utc).isoformat()),
        )
    await interaction.response.send_message(f"Saved a note for **{member}**.", ephemeral=True)


@bot.tree.command(description="List saved notes about a member.")
@app_commands.describe(member="Member whose notes you want to view.")
@app_commands.checks.has_permissions(manage_guild=True)
async def notes(interaction: discord.Interaction, member: discord.Member) -> None:
    with database() as connection:
        rows = connection.execute(
            "SELECT content, created_at FROM notes WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 10",
            (interaction.guild_id, member.id),
        ).fetchall()
    if not rows:
        await interaction.response.send_message("No notes found.", ephemeral=True)
        return
    text = "\n".join(f"• {row['content']} — {row['created_at'][:10]}" for row in rows)
    await interaction.response.send_message(f"**Notes for {member}:**\n{text}", ephemeral=True)


@bot.tree.command(description="List the bot's commands.")
async def help(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "**MultiTool commands**\n"
        "`/ping` `/serverinfo` `/userinfo` `/poll` `/remind`\n"
        "`/clear` `/kick` `/ban` `/note_add` `/notes`"
    )


@tasks.loop(seconds=15)
async def reminder_loop() -> None:
    now = datetime.now(timezone.utc)
    with database() as connection:
        rows = connection.execute(
            "SELECT id, channel_id, user_id, message FROM reminders WHERE due_at <= ?",
            (now.isoformat(),),
        ).fetchall()
        if rows:
            connection.executemany("DELETE FROM reminders WHERE id = ?", [(row["id"],) for row in rows])
    for row in rows:
        channel = bot.get_channel(row["channel_id"])
        if channel and hasattr(channel, "send"):
            await channel.send(f"<@{row['user_id']}> ⏰ Reminder: {row['message']}")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        message = "You do not have permission to use that command."
    else:
        log.exception("Command failed", exc_info=error)
        message = "Something went wrong while running that command."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Missing DISCORD_TOKEN. Copy .env.example to .env and add your bot token.")
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        pass