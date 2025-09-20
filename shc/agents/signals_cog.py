"""Signals agent."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Dict, Iterable, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import config, routing, state
from ..llm import nemotron_client
from ..market import providers

LOGGER = logging.getLogger(__name__)

MODE_CHANNEL = {
    "intraday": "alerts_day_trade",
    "swing": "alerts_swing",
    "leaps": "alerts_leaps",
    "longterm": "alerts_longterm",
}

signals_group = app_commands.Group(name="signals", description="Control the signals agent")


class SignalsCog(commands.Cog):
    """Slash commands for signals and scans."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._paused = False
        self._window = deque(maxlen=64)
        state.set_agent_paused("signals", False)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(signals_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(signals_group.name, type=discord.AppCommandType.chat_input)

    @app_commands.command(name="signal", description="Send a single signal to the desk")
    @app_commands.describe(ticker="Ticker symbol", mode="Intraday | swing | leaps | longterm")
    @app_commands.guild_only()
    async def signal(self, interaction: discord.Interaction, ticker: str, mode: Optional[str] = "intraday") -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        mode_key = (mode or "intraday").lower()
        try:
            if not await self._ready_to_emit(interaction, mode_key):
                return
            signal_payload = await self._build_signal_payload([ticker], mode_key)
            if not signal_payload:
                await interaction.followup.send(f"No data for {ticker.upper()}", ephemeral=True)
                return
            await self._dispatch_signals(mode_key, signal_payload)
            await interaction.followup.send("Signal dispatched", ephemeral=True)
        except Exception as exc:  # pragma: no cover - defensive for runtime
            LOGGER.exception("Signal command failed: %s", exc)
            state.mark_error("signals", str(exc))
            await interaction.followup.send("Signal failed – check logs", ephemeral=True)

    @app_commands.command(name="scan", description="Scan a universe and publish ranked signals")
    @app_commands.describe(mode="intraday | swing | leaps", universe="Comma separated tickers")
    @app_commands.guild_only()
    async def scan(self, interaction: discord.Interaction, mode: str, universe: Optional[str] = None) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        mode_key = (mode or "intraday").lower()
        try:
            if not await self._ready_to_emit(interaction, mode_key):
                return
            tickers = self._determine_universe(mode_key, universe)
            payload = await self._build_signal_payload(tickers, mode_key)
            if not payload:
                await interaction.followup.send("Nothing actionable found.", ephemeral=True)
                return
            await self._dispatch_signals(mode_key, payload)
            await interaction.followup.send(f"Published {len(payload)} signals", ephemeral=True)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Scan command failed: %s", exc)
            state.mark_error("signals", str(exc))
            await interaction.followup.send("Scan failed – check logs", ephemeral=True)

    @signals_group.command(name="pause")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        self._paused = True
        state.set_agent_paused("signals", True)
        await interaction.response.send_message("Signals agent paused", ephemeral=True)

    @signals_group.command(name="resume")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        self._paused = False
        state.set_agent_paused("signals", False)
        await interaction.response.send_message("Signals agent resumed", ephemeral=True)

    async def _ready_to_emit(self, interaction: discord.Interaction, mode: str) -> bool:
        if self._paused:
            await interaction.followup.send("Signals agent is paused", ephemeral=True)
            return False
        if state.is_global_pause():
            await interaction.followup.send("Global pause enabled by ops", ephemeral=True)
            return False
        if state.kill_switch_enabled():
            await interaction.followup.send("Kill switch enabled", ephemeral=True)
            return False
        if not self._check_rate_limit():
            await interaction.followup.send("Rate limit reached. Try again shortly.", ephemeral=True)
            return False
        if mode not in MODE_CHANNEL:
            await interaction.followup.send("Unknown mode", ephemeral=True)
            return False
        return True

    def _check_rate_limit(self) -> bool:
        now = asyncio.get_event_loop().time()
        window_seconds = 60
        max_alerts = config.max_alerts_per_minute()
        while self._window and now - self._window[0] > window_seconds:
            self._window.popleft()
        if len(self._window) >= max_alerts:
            return False
        self._window.append(now)
        return True

    def _determine_universe(self, mode: str, universe: Optional[str]) -> List[str]:
        if universe:
            return [ticker.strip().upper() for ticker in universe.split(",") if ticker.strip()]
        if mode == "intraday":
            return ["SPY", "QQQ", "TSLA", "NVDA", "AAPL"]
        if mode == "swing":
            return ["AMD", "META", "MSFT", "GOOGL", "NFLX"]
        if mode == "leaps":
            return ["SMH", "XLK", "SHOP", "AVGO"]
        return ["SPY", "QQQ", "DIA"]

    async def _build_signal_payload(self, tickers: Iterable[str], mode: str) -> List[Dict]:
        quotes = await providers.fetch_quotes(tickers)
        if not quotes:
            return []
        option_flow = await providers.fetch_option_flow(quotes.keys())
        payload: List[Dict] = []
        for ticker, quote in quotes.items():
            price = quote.get("price") or 0.0
            pct = quote.get("percent_change", 0.0)
            vol = quote.get("volume", 0)
            flow = option_flow.get(ticker, [])
            flow_score = min(len(flow), 5)
            volume_score = min(vol / 1_000_000, 5)
            score = pct * 0.6 + volume_score * 0.3 + flow_score * 0.1
            rationale = f"Momentum {pct:+.2f}% | Vol {vol:,}"
            payload.append(
                {
                    "ticker": ticker,
                    "price": price,
                    "percent_change": pct,
                    "volume": vol,
                    "score": score,
                    "rationale": rationale,
                    "risk": config.default_risk_level(),
                    "mode": mode,
                }
            )
        payload.sort(key=lambda item: item.get("score", 0), reverse=True)
        top = payload[:5]
        return top

    async def _dispatch_signals(self, mode: str, signals: List[Dict]) -> None:
        summary = await nemotron_client.summarize_signals(signals)
        channel_key = MODE_CHANNEL.get(mode, "alerts_day_trade")
        lines = []
        for signal in signals:
            lines.append(
                (
                    f"**{signal['ticker']}** {mode.upper()} @ {signal['price']:.2f} "
                    f"Δ {signal['percent_change']:+.2f}% | Vol {signal['volume']:,} | Score {signal['score']:.2f}"
                )
            )
            state.record_signal(signal["ticker"], mode=mode, price=signal.get("price") or 0.0)
        message = "\n".join(lines)
        message += f"\nNemotron: {summary}"
        delivered = await routing.send(self.bot, channel_key, content=message)
        details = {"last_post": discord.utils.utcnow().isoformat()}
        if delivered:
            state.mark_run("signals", details=details)
        else:
            state.mark_error("signals", "delivery failed")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SignalsCog(bot))

