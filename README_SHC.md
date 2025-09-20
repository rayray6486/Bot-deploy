# Slum House Capital Discord System

This directory contains the Discord automation stack for Slum House Capital.
The bot is designed for a headless droplet deployment (systemd service) and
depends on the modules inside the `shc` package.

## Environment configuration

Create a `.env` file alongside `bot.py` with the following keys:

```
DISCORD_BOT_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_GUILD_ID=

# Optional bootstrap seeds – final values are persisted to data/config.json
ALERTS_DAY_TRADE_ID=
ALERTS_SWING_ID=
ALERTS_LEAPS_ID=
ALERTS_LONGTERM_ID=
NEWS_WIRE_ID=
HEARTBEAT_CHANNEL_ID=
OPS_CONSOLE_ID=

# Market data providers (any combination works)
ALPACA_API_KEY_ID=
ALPACA_API_SECRET_KEY=
FINNHUB_API_KEY=
POLYGON_API_KEY=

# LLM (local Nemotron via Ollama, optional OpenAI fallback)
OLLAMA_BASE_URL=http://127.0.0.1:11434
NEMOTRON_MODEL=nemotron-mini
NEMOTRON_TIMEOUT=20
OPENAI_API_KEY=

# Risk controls
MAX_ALERTS_PER_MIN=12
DEFAULT_RISK_LEVEL=balanced
MARKET=US
```

The bot persists runtime identifiers (channel IDs, webhook URLs, role IDs) to
`data/config.json`. This file is created automatically on first start if it does
not exist.

## Bootstrap workflow

1. Deploy the bot with the `.env` file in place and allow it to connect.
2. Run `/bootstrap full` in your Discord guild.
   * The bot will create the category + channel skeleton, required roles, and
     alert webhooks.
   * Channel and webhook IDs are written back to `data/config.json` so future
     restarts reuse them.
3. Use `/bootstrap channels`, `/bootstrap roles`, or `/bootstrap webhooks` if you
   need to run a sub-step again (e.g. after deleting a webhook).

## Agent controls

* **Signals agent** – `/signal` for a manual idea, `/scan` for a ranked sweep.
  Pause/resume the agent with `/signals pause` and `/signals resume`.
* **News agent** – register tickers with `/news watch AAPL TSLA` (accepts comma
  or space separated symbols). Pause streaming with `/news pause`.
* **Scheduler agent** – runs the heartbeat and market open/close routines.
  View the current health summary via `/ops status`.
* **Ops agent** – `/ops pause`, `/ops resume`, and `/ops kill-switch on|off`
  control the global posture. Use `/ops create-channel` to add ad-hoc rooms or
  `/ops archive` to freeze a channel.

## Nemotron summarisation

Signal payloads are summarised locally by Ollama using the `nemotron-mini`
model. If Ollama is unreachable the bot optionally falls back to OpenAI
(`OPENAI_API_KEY`). When both providers fail a heuristic summary is still
returned, ensuring alerts never block.

## Smoke tests

Basic smoke coverage is provided by `python -m py_compile bot.py` and by running
`python smoke_tests.py` which exercises key modules without external calls. Use
`pip install -U -r requirements.txt` inside a virtualenv before executing.

