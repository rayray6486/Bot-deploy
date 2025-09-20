"""Market data provider helpers."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, Iterable, List, Optional

import aiohttp

from .. import config

LOGGER = logging.getLogger(__name__)

YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_EARNINGS_URL = "https://query1.finance.yahoo.com/v7/finance/calendar/earnings"


async def fetch_quotes(tickers: Iterable[str]) -> Dict[str, Dict]:
    """Fetch quote data for the provided tickers using the fastest available provider."""

    tickers = sorted({ticker.upper() for ticker in tickers if ticker})
    if not tickers:
        return {}

    params = {"symbols": ",".join(tickers)}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(YAHOO_QUOTE_URL, params=params) as response:
                if response.status != 200:
                    LOGGER.warning("Quote lookup failed (%s)", response.status)
                    return {}
                payload = await response.json()
    except aiohttp.ClientError as exc:
        LOGGER.error("Quote lookup error: %s", exc)
        return {}

    result: Dict[str, Dict] = {}
    for entry in payload.get("quoteResponse", {}).get("result", []):
        ticker = entry.get("symbol")
        if not ticker:
            continue
        price = entry.get("regularMarketPrice")
        change = entry.get("regularMarketChange", 0.0)
        percent = entry.get("regularMarketChangePercent", 0.0)
        volume = entry.get("regularMarketVolume") or 0
        previous_close = entry.get("regularMarketPreviousClose")
        result[ticker.upper()] = {
            "ticker": ticker.upper(),
            "price": float(price) if price is not None else None,
            "change": float(change) if change is not None else 0.0,
            "percent_change": float(percent) if percent is not None else 0.0,
            "volume": int(volume) if volume is not None else 0,
            "previous_close": float(previous_close) if previous_close is not None else None,
            "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        }
    return result


async def fetch_option_flow(tickers: Iterable[str]) -> Dict[str, List[Dict]]:
    """Return lightweight option flow. Placeholder implementation until providers enabled."""

    tickers = [ticker.upper() for ticker in tickers if ticker]
    if not tickers:
        return {}

    api_key = config.env("POLYGON_API_KEY") or config.env("FINNHUB_API_KEY")
    if not api_key:
        return {ticker: [] for ticker in tickers}

    # Placeholder: call Polygon news endpoint if key available.
    # This keeps structure ready for richer integration without failing.
    return {ticker: [] for ticker in tickers}


async def today_earnings() -> List[Dict]:
    """Fetch today's earnings calendar if available."""

    today = dt.date.today().isoformat()
    params = {"from": today, "to": today}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(YAHOO_EARNINGS_URL, params=params) as response:
                if response.status != 200:
                    return []
                payload = await response.json()
    except aiohttp.ClientError as exc:
        LOGGER.error("Earnings lookup failed: %s", exc)
        return []

    events = []
    for result in payload.get("finance", {}).get("result", []) or []:
        for item in result.get("calendarEvents", {}).get("earnings", {}).get("earningsDate", []):
            symbol = result.get("symbol")
            if not symbol:
                continue
            events.append(
                {
                    "ticker": symbol.upper(),
                    "when": item.get("fmt"),
                    "eps_estimate": result.get("epsEstimate"),
                    "eps_actual": result.get("epsActual"),
                }
            )
    return events


async def market_calendar() -> Dict[str, Optional[str]]:
    """Return today's basic market calendar."""

    today = dt.date.today()
    open_time = dt.datetime.combine(today, dt.time(hour=9, minute=30), tzinfo=dt.timezone.utc)
    close_time = dt.datetime.combine(today, dt.time(hour=16, minute=0), tzinfo=dt.timezone.utc)
    is_weekend = today.weekday() >= 5
    return {
        "market": config.market("US"),
        "is_holiday": str(is_weekend),
        "open": open_time.isoformat().replace("+00:00", "Z"),
        "close": close_time.isoformat().replace("+00:00", "Z"),
    }


__all__ = ["fetch_option_flow", "fetch_quotes", "market_calendar", "today_earnings"]

