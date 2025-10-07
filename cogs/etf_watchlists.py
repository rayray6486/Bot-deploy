import discord
from discord import app_commands
from discord.ext import commands

DEFAULTS = ["SPY", "QQQ", "SOXX"]

class ETFWatchlists(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="watchlist", description="Show tracked ETFs.")
    async def watchlist(self, interaction: discord.Interaction):
        await interaction.response.send_message("Tracked ETFs: " + ", ".join(DEFAULTS))

async def setup(bot):
    await bot.add_cog(ETFWatchlists(bot))
