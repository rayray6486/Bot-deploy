# bot.py
import logging, os, asyncio
from pathlib import Path
from dotenv import load_dotenv
import discord
from discord.ext import commands

# ---- env & logging ---------------------------------------------------------
load_dotenv(dotenv_path=Path(".env") if Path(".env").exists() else None)

DISCORD_TOKEN           = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_ID        = int(os.getenv("DISCORD_GUILD_ID", "0")) or None
DISCORD_ALERT_CHANNEL_ID= int(os.getenv("DISCORD_ALERT_CHANNEL_ID", "0")) or None
ADMIN_USER_ID           = int(os.getenv("ADMIN_USER_ID", "0")) or None

# fail early if token missing
if not DISCORD_TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN in .env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("slumhouse.bot")

# ---- bot client ------------------------------------------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = False  # keep safe; enable if needed later

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- startup & sync --------------------------------------------------------
@bot.event
async def on_ready():
    log.info(f"Bot is online as {bot.user} (id={bot.user.id})")
    try:
        # guild-only sync if provided, otherwise global
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=DISCORD_GUILD_ID)
            await bot.tree.sync(guild=guild)
            log.info(f"Synced commands to guild {DISCORD_GUILD_ID}")
        else:
            await bot.tree.sync()
            log.info("Synced global commands")
    except Exception as e:
        log.exception("Slash command sync failed: %s", e)

# ---- basic slash commands --------------------------------------------------
@bot.tree.command(name="ping", description="Health check")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 pong", ephemeral=True)

@bot.tree.command(name="set-alert-channel", description="Set this channel for alerts")
async def set_alert_channel(interaction: discord.Interaction):
    global DISCORD_ALERT_CHANNEL_ID
    if ADMIN_USER_ID and interaction.user.id != ADMIN_USER_ID:
        return await interaction.response.send_message("Admins only.", ephemeral=True)
    DISCORD_ALERT_CHANNEL_ID = interaction.channel.id
    await interaction.response.send_message("✅ Alerts will post in this channel.", ephemeral=True)

# ---- load cogs -------------------------------------------------------------
async def load_cogs():
    for name in ("cogs.admin", "cogs.alerts", "cogs.market"):
        try:
            await bot.load_extension(name)
            log.info("Loaded %s", name)
        except Exception as e:
            log.exception("Failed loading %s: %s", name, e)

async def main():
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
