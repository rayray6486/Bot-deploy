# cogs/admin.py
import os, discord
from discord.ext import commands

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0")) or None

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # send a hello in the first text channel we can post in
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                await ch.send("👋 Slum House Capital bot installed. Use `/set-alert-channel` in the channel you want alerts.")
                break

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
