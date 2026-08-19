# Discord MultiTool Bot

A lightweight, modular Discord bot written in Python for Termux and other Linux environments.

## Features

- `/ping` — check latency
- `/serverinfo` — show server details
- `/userinfo` — inspect a member
- `/poll` — create a reaction-based poll
- `/remind` — schedule a reminder such as `10m`, `2h`, or `1d`
- `/clear` — bulk-delete recent messages (Manage Messages permission)
- `/kick` and `/ban` — moderation commands
- `/note_add` and `/notes` — save and view per-user server notes
- `/help` — list commands

## Termux install

```bash
pkg update -y
pkg install python git -y
git clone https://github.com/kokhkhjhchfjhh-sys/discord-multitool-bot.git
cd discord-multitool-bot
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
python bot.py
```

For a persistent session, use `tmux`:

```bash
pkg install tmux -y
tmux new -s discordbot
python bot.py
# Detach with Ctrl+B, then D
```

## Discord setup

1. Create an application at https://discord.com/developers/applications.
2. Create a bot and copy its token into `.env`.
3. Enable **Message Content Intent** only if you plan to add prefix commands later. This project uses slash commands, so it is not required.
4. Invite the bot with the `bot` and `applications.commands` scopes.
5. Give it only the permissions it needs. Moderation commands require the matching Discord permissions.

After inviting the bot, slash commands may take up to an hour to appear globally. Set `DISCORD_GUILD_ID` in `.env` while testing for near-instant registration in one server.

## Configuration

```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=
DATABASE_PATH=bot.sqlite3
```

Never commit `.env` or your bot token.

## Run

```bash
python bot.py
```

Stop it with `Ctrl+C`.

## Safety

The bot does not include self-bot behavior, token scraping, mass messaging, raid features, or automatic moderation. Use it only in servers where you have permission to operate a bot.

## License

MIT