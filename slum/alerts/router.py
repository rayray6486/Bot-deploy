"""Alert routing utilities."""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Dict, Optional

from types import SimpleNamespace

try:  # pragma: no cover - exercised in tests without discord.py installed
    import discord
    from discord.errors import DiscordServerError, Forbidden, HTTPException, NotFound
except ModuleNotFoundError:  # pragma: no cover
    class _StubClient:
        def get_channel(self, channel_id):
            return None

        async def fetch_channel(self, channel_id):
            return None

    class _StubEmbed:
        def __init__(self, title: Optional[str] = None, description: Optional[str] = None):
            self.title = title
            self.description = description

        @classmethod
        def from_dict(cls, payload: Dict[str, Any]) -> "_StubEmbed":
            return cls(title=payload.get("title"), description=payload.get("description"))

    discord = SimpleNamespace(Client=_StubClient, Embed=_StubEmbed, TextChannel=object, Member=object)  # type: ignore

    class HTTPException(Exception):
        pass

    class DiscordServerError(HTTPException):
        pass

    class Forbidden(HTTPException):
        pass

    class NotFound(HTTPException):
        pass

from .config import CHANNEL_KEYS, CHANNEL_CONFIG_PATH, ChannelConfig

LOGGER = logging.getLogger(__name__)

CLIENT: Optional[discord.Client] = None
_CHANNEL_CONFIG: ChannelConfig = ChannelConfig.load()

ALERT_TYPE_TO_KEY = {
    "day": "day_trade_alerts",
    "swing": "swing_alerts",
    "leaps": "leaps_alerts",
    "long_term": "long_term_alerts",
    "news": "news_feed",
}


class OpsLogger:
    """Helper that mirrors exceptions to the ops logs channel."""

    def __init__(self) -> None:
        self.channel_id: Optional[int] = None

    def refresh(self, config: Optional[ChannelConfig] = None) -> None:
        config = config or get_channel_config()
        self.channel_id = config.get("ops_logs")

    async def exception(self, message: str, error: BaseException) -> None:
        LOGGER.exception(message, exc_info=error)
        if not self.channel_id:
            return
        trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        description = trace[-3500:]
        embed = discord.Embed(title="Exception", description=f"```{description}```")
        content = f"⚠️ {message}"
        try:
            await safe_send(self.channel_id, content[:2000], embed=embed)
        except Exception:  # pragma: no cover - avoid infinite recursion
            LOGGER.exception("Failed to post ops log message")


OPS_LOGGER = OpsLogger()
OPS_LOGGER.refresh(_CHANNEL_CONFIG)


def configure(bot: Optional[discord.Client], config: Optional[ChannelConfig] = None) -> None:
    """Configure the router with a Discord client and configuration."""

    global CLIENT
    CLIENT = bot
    if config is not None:
        set_channel_config(config)
    elif _CHANNEL_CONFIG is None:
        set_channel_config(ChannelConfig.load())


def get_channel_config() -> ChannelConfig:
    return _CHANNEL_CONFIG


def set_channel_config(config: ChannelConfig) -> ChannelConfig:
    global _CHANNEL_CONFIG
    _CHANNEL_CONFIG = config
    OPS_LOGGER.refresh(config)
    return _CHANNEL_CONFIG


def reload_config(path: Optional[str | ChannelConfig] = None) -> ChannelConfig:
    target_path = None
    if isinstance(path, ChannelConfig):
        target_path = path.path
    elif isinstance(path, (str, bytes)):
        target_path = path
    elif path is None:
        target_path = _CHANNEL_CONFIG.path if _CHANNEL_CONFIG else CHANNEL_CONFIG_PATH
    config = ChannelConfig.load(target_path)
    return set_channel_config(config)


def update_channel(key: str, channel_id: Optional[int]) -> ChannelConfig:
    if key not in CHANNEL_KEYS:
        raise KeyError(key)
    config = get_channel_config()
    config.set(key, channel_id)
    config.save()
    return reload_config(config)


async def route_alert(alert: Dict[str, Any]) -> Optional[discord.Message]:
    """Send an alert payload to its mapped Discord channel."""

    alert_type = (alert.get("type") or "").lower()
    if alert_type not in ALERT_TYPE_TO_KEY:
        raise ValueError(f"Unsupported alert type: {alert_type!r}")
    config_key = ALERT_TYPE_TO_KEY[alert_type]
    channel_id = get_channel_config().get(config_key)
    if not channel_id:
        LOGGER.warning("No channel configured for alert type %s", alert_type)
        return None

    content = alert.get("content") or alert.get("message") or ""
    embed_payload = alert.get("embed")
    embed = None
    if embed_payload:
        embed = discord.Embed.from_dict(embed_payload)
    return await safe_send(channel_id, content, embed=embed)


async def safe_send(
    channel_id: int,
    content: str,
    *,
    embed: Optional[discord.Embed] = None,
    max_attempts: int = 4,
    base_delay: float = 1.0,
) -> Optional[discord.Message]:
    """Send a message with retries and exponential backoff."""

    if CLIENT is None:
        raise RuntimeError("Alert router has not been configured with a Discord client")

    attempt = 0
    last_error: Optional[BaseException] = None
    while attempt < max_attempts:
        attempt += 1
        try:
            channel = CLIENT.get_channel(int(channel_id)) if hasattr(CLIENT, "get_channel") else None
            if channel is None and hasattr(CLIENT, "fetch_channel"):
                channel = await CLIENT.fetch_channel(int(channel_id))
            if channel is None or not hasattr(channel, "send"):
                raise RuntimeError(f"Unable to resolve channel {channel_id}")
            return await channel.send(content, embed=embed)
        except (HTTPException, DiscordServerError) as exc:
            last_error = exc
            LOGGER.warning(
                "Discord API error when sending to %s (attempt %s/%s): %s",
                channel_id,
                attempt,
                max_attempts,
                exc,
            )
        except (Forbidden, NotFound) as exc:
            LOGGER.error("Permission error sending to channel %s: %s", channel_id, exc)
            raise
        except Exception as exc:  # pragma: no cover - unexpected error path
            last_error = exc
            LOGGER.exception("Unexpected error when sending to channel %s", channel_id)
        if attempt < max_attempts:
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    if last_error:
        raise last_error
    return None

