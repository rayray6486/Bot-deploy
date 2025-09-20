"""Configuration utilities for Slum House Capital."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, MutableMapping, Optional

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - lightweight fallback for smoke tests
    def load_dotenv(*_, **__):  # type: ignore
        LOGGER.warning("python-dotenv not installed; skipping .env load.")
        return False

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "config.json"

_ENV_LOCK = threading.Lock()
_CONFIG_LOCK = threading.Lock()
_ENV_LOADED = False
_RUNTIME_CACHE: Optional[Dict[str, Any]] = None

_CHANNEL_ENV_MAP = {
    "alerts_day_trade": "ALERTS_DAY_TRADE_ID",
    "alerts_swing": "ALERTS_SWING_ID",
    "alerts_leaps": "ALERTS_LEAPS_ID",
    "alerts_longterm": "ALERTS_LONGTERM_ID",
    "news_wire": "NEWS_WIRE_ID",
    "heartbeat": "HEARTBEAT_CHANNEL_ID",
    "ops_console": "OPS_CONSOLE_ID",
}


def load_env(dotenv_path: Optional[Path] = None) -> MutableMapping[str, str]:
    """Ensure that .env variables are loaded exactly once."""

    global _ENV_LOADED
    with _ENV_LOCK:
        if not _ENV_LOADED:
            try:
                load_dotenv(dotenv_path)
                LOGGER.debug("Environment loaded from %s", dotenv_path or ".env")
            finally:
                _ENV_LOADED = True
    return os.environ


def env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get an environment variable after ensuring the .env has been loaded."""

    load_env()
    return os.getenv(key, default)


def ensure_data_dir() -> None:
    """Create the runtime data directory if needed."""

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - extremely rare on droplet
        LOGGER.error("Unable to create data directory %s: %s", DATA_DIR, exc)
        raise


def _default_runtime_config() -> Dict[str, Any]:
    return {
        "guild_id": None,
        "channels": {},
        "webhooks": {},
        "roles": {},
    }


def _load_runtime_config() -> Dict[str, Any]:
    global _RUNTIME_CACHE
    with _CONFIG_LOCK:
        if _RUNTIME_CACHE is not None:
            return _RUNTIME_CACHE

        ensure_data_dir()
        if CONFIG_FILE.exists():
            try:
                _RUNTIME_CACHE = json.loads(CONFIG_FILE.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                LOGGER.warning("Failed to load %s: %s. Reinitialising.", CONFIG_FILE, exc)
                _RUNTIME_CACHE = _default_runtime_config()
        else:
            _RUNTIME_CACHE = _default_runtime_config()
            _write_runtime_config(_RUNTIME_CACHE)
        return _RUNTIME_CACHE


def _write_runtime_config(data: Dict[str, Any]) -> None:
    ensure_data_dir()
    try:
        CONFIG_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))
    except OSError as exc:  # pragma: no cover - disk write issues are fatal
        LOGGER.error("Unable to write runtime config %s: %s", CONFIG_FILE, exc)
        raise


def runtime_config() -> Dict[str, Any]:
    """Return a copy of the cached runtime configuration."""

    data = _load_runtime_config()
    return json.loads(json.dumps(data))


def _update_runtime(section: str, key: str, value: Any) -> None:
    data = _load_runtime_config()
    with _CONFIG_LOCK:
        target = data.setdefault(section, {})
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value
        _write_runtime_config(data)


def guild() -> Optional[int]:
    data = _load_runtime_config()
    guild_id = data.get("guild_id")
    if guild_id:
        return int(guild_id)
    env_value = env("DISCORD_GUILD_ID")
    return int(env_value) if env_value else None


def set_guild(guild_id: int) -> None:
    data = _load_runtime_config()
    with _CONFIG_LOCK:
        data["guild_id"] = int(guild_id)
        _write_runtime_config(data)


def client_id() -> Optional[int]:
    value = env("DISCORD_CLIENT_ID")
    return int(value) if value else None


def bot_token() -> str:
    token = env("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")
    return token


def channel_id(key: str) -> Optional[int]:
    key = key.lower()
    data = _load_runtime_config()
    channel_map = data.setdefault("channels", {})
    if key in channel_map and channel_map[key]:
        return int(channel_map[key])
    env_key = _CHANNEL_ENV_MAP.get(key)
    if env_key:
        env_value = env(env_key)
        if env_value:
            try:
                value = int(env_value)
            except ValueError:
                LOGGER.warning("Invalid channel id for %s in env: %s", key, env_value)
            else:
                set_channel_id(key, value)
                return value
    return None


def set_channel_id(key: str, value: Optional[int]) -> None:
    key = key.lower()
    numeric = int(value) if value is not None else None
    _update_runtime("channels", key, numeric)


def webhook_url(key: str) -> Optional[str]:
    data = _load_runtime_config()
    url = data.get("webhooks", {}).get(key.lower())
    return url


def set_webhook_url(key: str, value: Optional[str]) -> None:
    _update_runtime("webhooks", key.lower(), value)


def role_id(key: str) -> Optional[int]:
    data = _load_runtime_config()
    role_map = data.get("roles", {})
    value = role_map.get(key.lower())
    return int(value) if value else None


def set_role_id(key: str, value: Optional[int]) -> None:
    numeric = int(value) if value is not None else None
    _update_runtime("roles", key.lower(), numeric)


def max_alerts_per_minute(default: int = 12) -> int:
    value = env("MAX_ALERTS_PER_MIN", str(default))
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        LOGGER.warning("Invalid MAX_ALERTS_PER_MIN: %s", value)
        return default


def default_risk_level(default: str = "balanced") -> str:
    value = env("DEFAULT_RISK_LEVEL", default)
    return (value or default).lower()


def market(default: str = "US") -> str:
    value = env("MARKET", default)
    return (value or default).upper()


def ensure_runtime_config() -> Dict[str, Any]:
    """Expose the live runtime config, ensuring the file exists."""

    return _load_runtime_config()


__all__ = [
    "bot_token",
    "channel_id",
    "client_id",
    "default_risk_level",
    "ensure_runtime_config",
    "env",
    "guild",
    "load_env",
    "market",
    "max_alerts_per_minute",
    "role_id",
    "runtime_config",
    "set_channel_id",
    "set_guild",
    "set_role_id",
    "set_webhook_url",
    "webhook_url",
]

