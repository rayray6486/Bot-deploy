  import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# Load .env if present (useful on the droplet where we create it)
load_dotenv(dotenv_path=Path(".env") if Path(".env").exists() else None)

# === your exact secret names ===
DISCORD_TOKEN            = os.getenv("DISCORD_BOT_TOKEN")         # token string
DISCORD_CLIENT_ID        = os.getenv("DISCORD_CLIENT_ID")         # app id
DISCORD_GUILD_ID         = os.getenv("DISCORD_GUILD_ID")          # optional: int(str)
DISCORD_ALERT_CHANNEL_ID = os.getenv("DISCORD_ALERT_CHANNEL_ID")  # optional: int(str)

ADMIN_USER_ID            = os.getenv("ADMIN_USER_ID")

STRIPE_SECRET_KEY        = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY   = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET    = os.getenv("STRIPE_WEBHOOK_SECRET")

FINNHUB_API_KEY          = os.getenv("FINNHUB_API_KEY")

ALPACA_API_KEY_ID        = os.getenv("ALPACA_API_KEY_ID")
ALPACA_API_SECRET_KEY    = os.getenv("ALPACA_API_SECRET_KEY", "")  # if you add later
ALPACA_API_BASE_URL      = os.getenv("ALPACA_API_BASE_URL")

OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY")

# Basic sanity (fail fast if a must-have is missing)
missing = [k for k,v in {
    "DISCORD_BOT_TOKEN":DISCORD_TOKEN,
    "STRIPE_SECRET_KEY":STRIPE_SECRET_KEY,
}.items() if not v]
if missing:
    raise SystemExit(f"Missing required secret(s): {', '.join(missing)}")
