"""Channel configuration loader."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, MutableMapping, Optional

CHANNEL_CONFIG_PATH = Path("config/channels.yml")

ENVIRONMENT_OVERRIDES = {
    "day_trade_alerts": "DAY_TRADE_CHANNEL_ID",
    "swing_alerts": "SWING_CHANNEL_ID",
    "leaps_alerts": "LEAPS_CHANNEL_ID",
    "long_term_alerts": "LONG_TERM_CHANNEL_ID",
    "news_feed": "NEWS_CHANNEL_ID",
    "ops_logs": "OPS_LOG_CHANNEL_ID",
}

CHANNEL_KEYS = tuple(ENVIRONMENT_OVERRIDES.keys())


def _coerce_channel_id(value: Optional[object]) -> Optional[int]:
    """Normalize a value loaded from YAML or the environment."""

    if value is None:
        return None
    if isinstance(value, int):
        return value or None
    text = str(value).strip()
    if not text or text == "0":
        return None
    try:
        return int(text)
    except ValueError:
        return None


@dataclass(slots=True)
class ChannelConfig:
    """Simple container for alert channel identifiers."""

    values: Dict[str, Optional[int]] = field(default_factory=dict)
    path: Path = field(default_factory=lambda: CHANNEL_CONFIG_PATH)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        for key in CHANNEL_KEYS:
            self.values.setdefault(key, None)
            coerced = _coerce_channel_id(self.values[key])
            self.values[key] = coerced

    @classmethod
    def load(
        cls,
        path: Path | str = CHANNEL_CONFIG_PATH,
        env: MutableMapping[str, str] | None = None,
    ) -> "ChannelConfig":
        env = env or os.environ
        path = Path(path)
        data: Dict[str, Optional[int]] = {key: None for key in CHANNEL_KEYS}
        if path.exists():
            loaded = _read_simple_mapping(path)
            for key in CHANNEL_KEYS:
                data[key] = _coerce_channel_id(loaded.get(key))
        for key, env_name in ENVIRONMENT_OVERRIDES.items():
            env_value = env.get(env_name)
            if env_value:
                data[key] = _coerce_channel_id(env_value)
        return cls(data, path)

    def get(self, key: str) -> Optional[int]:
        if key not in CHANNEL_KEYS:
            raise KeyError(key)
        return self.values.get(key)

    def set(self, key: str, value: Optional[int]) -> None:
        if key not in CHANNEL_KEYS:
            raise KeyError(key)
        self.values[key] = _coerce_channel_id(value)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for key in CHANNEL_KEYS:
            value = self.values.get(key)
            rendered = "" if value is None else str(value)
            lines.append(f"{key}: \"{rendered}\"")
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def as_dict(self) -> Dict[str, Optional[int]]:
        return {key: self.values.get(key) for key in CHANNEL_KEYS}


def _read_simple_mapping(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        data[key] = value
    return data

