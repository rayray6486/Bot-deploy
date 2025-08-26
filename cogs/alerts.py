# cogs/alerts.py
import os, datetime
from zoneinfo import ZoneInfo
from discord.ext import commands, tasks
import discord

ALERT_CHANNEL_ID = int(os.getenv("DISCORD_ALERT_CHANNEL_ID", "0")) or None
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))

class Alerts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.market_open_alert.start()

    def cog_unload(self):
        self.market_open_alert.cancel()

    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=TZ))
    async def market_open_alert(self):
        if not ALERT_CHANNEL_ID:
            return
        ch = self.bot.get_channel(ALERT_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            await ch.send("📈 Good morning! Market opens at 9:30 ET. Watch your levels. 💵")

    @market_open_alert.before_loop
    async def before_market_open(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Alerts(bot))
