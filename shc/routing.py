"""Message routing helpers."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, Optional

import aiohttp
import discord

from . import config, state

LOGGER = logging.getLogger(__name__)

CHANNEL_NAMES: Dict[str, str] = {
    "alerts_day_trade": "alerts-day-trade",
    "alerts_swing": "alerts-swing",
    "alerts_leaps": "alerts-leaps",
    "alerts_longterm": "alerts-longterm",
    "news_wire": "news-wire",
    "ops_console": "ops-console",
    "heartbeat": "heartbeat",
    "market_open": "market-open",
    "market_close": "market-close",
}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def send(bot: discord.Client, channel_key: str, *, content: Optional[str] = None, embeds: Optional[list[discord.Embed]] = None, username: Optional[str] = None, avatar_url: Optional[str] = None, allowed_mentions: Optional[discord.AllowedMentions] = None, **kwargs: Any) -> bool:
    """Send a message to the configured destination, preferring webhooks."""

    if state.kill_switch_enabled():
        LOGGER.warning("Kill switch enabled – dropping message for %s", channel_key)
        return False

    url = config.webhook_url(channel_key)
    if url:
        delivered = await _send_via_webhook(url, content=content, embeds=embeds, username=username, avatar_url=avatar_url, allowed_mentions=allowed_mentions, **kwargs)
        if delivered:
            return True

    channel_obj = await _resolve_channel(bot, channel_key)
    if channel_obj is None:
        LOGGER.error("No channel resolved for key %s", channel_key)
        return False

    try:
        await channel_obj.send(content=content, embeds=embeds, allowed_mentions=allowed_mentions, **kwargs)
        return True
    except discord.HTTPException as exc:
        LOGGER.error("Failed to send message to %s (%s): %s", channel_key, channel_obj.id, exc)
    return False


async def _resolve_channel(bot: discord.Client, channel_key: str) -> Optional[discord.TextChannel]:
    channel_id = config.channel_id(channel_key)
    if not channel_id:
        return None
    channel = bot.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    try:
        fetched = await bot.fetch_channel(channel_id)
    except discord.HTTPException as exc:
        LOGGER.error("Failed to fetch channel %s: %s", channel_id, exc)
        return None
    if isinstance(fetched, discord.TextChannel):
        return fetched
    LOGGER.warning("Channel %s for key %s is not a text channel", channel_id, channel_key)
    return None


async def _send_via_webhook(url: str, *, content: Optional[str], embeds: Optional[list[discord.Embed]], username: Optional[str], avatar_url: Optional[str], allowed_mentions: Optional[discord.AllowedMentions], **kwargs: Any) -> bool:
    payload_kwargs = {"wait": False, **kwargs}
    for attempt in range(4):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                webhook = discord.Webhook.from_url(url, session=session)
                await webhook.send(content=content, embeds=embeds, username=username, avatar_url=avatar_url, allowed_mentions=allowed_mentions, **payload_kwargs)
                return True
        except discord.HTTPException as exc:
            if exc.status in RETRYABLE_STATUS and attempt < 3:
                delay = 1.5 + random.random() * 2
                LOGGER.warning("Webhook send failed (%s). Retrying in %.2fs", exc.status, delay)
                await asyncio.sleep(delay)
                continue
            LOGGER.error("Webhook send error for %s: %s", url, exc)
            return False
        except aiohttp.ClientError as exc:
            delay = 1.0 + random.random()
            LOGGER.warning("Webhook network error: %s. Retrying in %.2fs", exc, delay)
            await asyncio.sleep(delay)
    return False


__all__ = ["send", "CHANNEL_NAMES"]

