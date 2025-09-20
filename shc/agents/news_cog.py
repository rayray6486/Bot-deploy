"""News agent."""

from __future__ import annotations

import logging
from typing import Dict, List, Set

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import routing, state

LOGGER = logging.getLogger(__name__)

news_group = app_commands.Group(name="news", description="Market news controls")


class NewsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._watchlist: Set[str] = set()
        self._paused = False
        self._seen: Set[str] = set()

    async def cog_load(self) -> None:
        self.bot.tree.add_command(news_group)
        self.poll_news.start()

    async def cog_unload(self) -> None:
        self.poll_news.cancel()
        self.bot.tree.remove_command(news_group.name, type=discord.AppCommandType.chat_input)

    @news_group.command(name="watch")
    @app_commands.describe(tickers="Space or comma separated tickers to monitor")
    @app_commands.guild_only()
    async def watch(self, interaction: discord.Interaction, tickers: str) -> None:
        symbols = {token.strip().upper() for token in tickers.replace(",", " ").split() if token.strip()}
        if not symbols:
            await interaction.response.send_message("No tickers provided", ephemeral=True)
            return
        self._watchlist.update(symbols)
        self._paused = False
        state.set_agent_paused("news", False)
        await interaction.response.send_message(f"Watching {', '.join(sorted(self._watchlist))}", ephemeral=True)

    @news_group.command(name="pause")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        self._paused = True
        state.set_agent_paused("news", True)
        await interaction.response.send_message("News agent paused", ephemeral=True)

    @tasks.loop(minutes=3)
    async def poll_news(self) -> None:
        if not self._watchlist or self._paused:
            return
        if state.is_global_pause() or state.kill_switch_enabled():
            return
        await self._run_cycle()

    @poll_news.before_loop
    async def before_poll(self) -> None:
        await self.bot.wait_until_ready()

    async def _run_cycle(self) -> None:
        tickers = list(self._watchlist)
        timeout = aiohttp.ClientTimeout(total=8)
        new_items: List[Dict] = []
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for ticker in tickers:
                    items = await self._fetch_for_ticker(session, ticker)
                    new_items.extend(items)
        except aiohttp.ClientError as exc:
            LOGGER.error("News fetch failed: %s", exc)
            state.mark_error("news", str(exc))
            return

        if not new_items:
            return

        new_items.sort(key=lambda item: item.get("published_at", 0), reverse=True)
        for item in new_items:
            identifier = item.get("id")
            if not identifier or identifier in self._seen:
                continue
            self._seen.add(identifier)
            headline = item.get("title")
            url = item.get("url")
            ticker = item.get("ticker")
            message = f"📰 **{ticker}** {headline}\n{url}"
            delivered = await routing.send(self.bot, "news_wire", content=message)
            details = {"last_post": discord.utils.utcnow().isoformat()}
            if delivered:
                state.mark_run("news", details=details)
            else:
                state.mark_error("news", "delivery failed")

    async def _fetch_for_ticker(self, session: aiohttp.ClientSession, ticker: str) -> List[Dict]:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        params = {"q": ticker, "newsCount": 6}
        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    LOGGER.debug("No news for %s (%s)", ticker, response.status)
                    return []
                payload = await response.json()
        except aiohttp.ClientError as exc:
            LOGGER.debug("Ticker %s news error: %s", ticker, exc)
            return []

        items: List[Dict] = []
        for entry in payload.get("news", []):
            uuid = entry.get("uuid") or entry.get("id") or entry.get("link")
            if not uuid:
                continue
            items.append(
                {
                    "id": uuid,
                    "ticker": ticker,
                    "title": entry.get("title", ""),
                    "url": entry.get("link"),
                    "published_at": entry.get("providerPublishTime", 0),
                }
            )
        return items


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NewsCog(bot))

