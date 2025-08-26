# cogs/market.py
import os, aiohttp, asyncio
from discord import app_commands, Interaction
from discord.ext import commands

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
ALPACA_API_KEY  = os.getenv("ALPACA_API_KEY_ID")
ALPACA_SECRET   = os.getenv("ALPACA_API_SECRET_KEY")
ALPACA_BASE     = os.getenv("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets")

class Market(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="price", description="Get the latest price for a symbol (e.g., AAPL, SPY).")
    @app_commands.describe(symbol="Ticker symbol")
    async def price(self, interaction: Interaction, symbol: str):
        symbol = symbol.upper().strip()
        await interaction.response.defer(thinking=True, ephemeral=True)

        price = None
        # Try Finnhub first if key is present
        if FINNHUB_API_KEY:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        price = data.get("c")

        # Fallback: Alpaca last trade (if keys present)
        if price is None and ALPACA_API_KEY and ALPACA_SECRET:
            url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest"
            headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers, timeout=10) as r:
                    if r.status == 200:
                        j = await r.json()
                        price = (j.get("trade") or {}).get("p")

        if price is None:
            return await interaction.followup.send(f"Couldn’t fetch `{symbol}` right now.", ephemeral=True)

        await interaction.followup.send(f"**{symbol}** ≈ **${price:.2f}**", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Market(bot))
