import os, asyncio, logging, discord
from discord.ext import commands

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("shc")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.guilds = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)
COGS = ["cogs.etf_watchlists"]

@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id)
    await bot.tree.sync()
    logger.info("Slash commands synced")

async def main():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            logger.info("Loaded cog: %s", cog)
        except Exception as e:
            logger.exception("Failed to load cog %s: %s", cog, e)

    token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN or DISCORD_BOT_TOKEN not set")
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
