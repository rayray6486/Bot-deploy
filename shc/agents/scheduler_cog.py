"""Scheduler agent."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, List

import discord
from discord.ext import commands, tasks

from .. import routing, state
from ..market import providers

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - zoneinfo always available in py3.10 but defensive for portability
    from zoneinfo import ZoneInfo

    EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    EASTERN = dt.timezone(dt.timedelta(hours=-4))


class SchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.heartbeat.start()
        self.pre_open.start()
        self.close_report.start()

    async def cog_unload(self) -> None:
        self.heartbeat.cancel()
        self.pre_open.cancel()
        self.close_report.cancel()

    @tasks.loop(minutes=10)
    async def heartbeat(self) -> None:
        statuses = list(state.all_statuses())
        if not statuses:
            content = "No agent activity yet."
        else:
            lines = ["🫀 **Agent heartbeat**"]
            for status in sorted(statuses, key=lambda s: s.name):
                last = status.last_success or status.last_run
                last_str = last.isoformat() if last else "n/a"
                error = f" ⚠️ {status.last_error}" if status.last_error else ""
                pause = " ⏸" if status.paused else ""
                lines.append(f"• {status.name}: {last_str}{pause}{error}")
            content = "\n".join(lines)
        delivered = await routing.send(self.bot, "heartbeat", content=content)
        details = {"last_post": discord.utils.utcnow().isoformat()}
        if delivered:
            state.mark_run("scheduler-heartbeat", details=details)
        else:
            state.mark_error("scheduler-heartbeat", "delivery failed")

    @heartbeat.before_loop
    async def before_heartbeat(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(time=dt.time(hour=9, minute=29, tzinfo=EASTERN))
    async def pre_open(self) -> None:
        now = dt.datetime.now(tz=EASTERN)
        if now.weekday() >= 5 or state.kill_switch_enabled():
            return
        if state.is_global_pause():
            LOGGER.info("Global pause active – skipping pre-open snapshot")
            return
        quotes = await providers.fetch_quotes(["SPY", "QQQ", "IWM", "DIA"])
        earnings = await providers.today_earnings()
        lines = ["📊 **Pre-market snapshot**"]
        for symbol in ["SPY", "QQQ", "IWM", "DIA"]:
            q = quotes.get(symbol)
            if not q:
                continue
            lines.append(
                f"{symbol}: {q.get('price', 0):.2f} ({q.get('percent_change', 0):+0.2f}%) Vol {q.get('volume', 0):,}"
            )
        if earnings:
            top = earnings[:5]
            lines.append("Earnings today: " + ", ".join(f"{item['ticker']}({item.get('when', '?')})" for item in top))
        calendar = await providers.market_calendar()
        lines.append(f"Market hours: {calendar.get('open')} → {calendar.get('close')}")
        delivered = await routing.send(self.bot, "market_open", content="\n".join(lines))
        details = {"last_post": discord.utils.utcnow().isoformat()}
        if delivered:
            state.mark_run("scheduler-preopen", details=details)
        else:
            state.mark_error("scheduler-preopen", "delivery failed")

    @pre_open.before_loop
    async def before_pre_open(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(time=dt.time(hour=16, minute=0, tzinfo=EASTERN))
    async def close_report(self) -> None:
        now = dt.datetime.now(tz=EASTERN)
        if now.weekday() >= 5:
            return
        if state.kill_switch_enabled() or state.is_global_pause():
            return
        signals = state.recent_signals(hours=8)
        tickers = [record.ticker for record in signals]
        quotes: Dict[str, Dict] = {}
        if tickers:
            quotes = await providers.fetch_quotes(tickers)
        lines: List[str] = ["🔔 **Market close summary**"]
        total_pnl = 0.0
        for record in signals:
            q = quotes.get(record.ticker, {})
            price = q.get("price")
            if price is None:
                continue
            pnl = price - record.price
            total_pnl += pnl
            lines.append(
                f"{record.ticker} {record.mode.upper()}: entry {record.price:.2f} → close {price:.2f} (Δ {pnl:+.2f})"
            )
        if not signals:
            lines.append("No tracked signals today.")
        lines.append(f"Simulated basket PnL: {total_pnl:+.2f}")
        delivered = await routing.send(self.bot, "market_close", content="\n".join(lines))
        details = {"last_post": discord.utils.utcnow().isoformat()}
        if delivered:
            state.mark_run("scheduler-close", details=details)
        else:
            state.mark_error("scheduler-close", "delivery failed")

    @close_report.before_loop
    async def before_close(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SchedulerCog(bot))

