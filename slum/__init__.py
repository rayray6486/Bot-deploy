"""Slum House bot utilities."""
from __future__ import annotations

import os
from typing import Optional

__all__ = ["get_version"]


def get_version(default: str = "dev") -> str:
    """Return the current bot version string.

    The value is derived from common deployment environment variables. If no
    known variable is set, *default* is returned.
    """

    for name in ("BOT_VERSION", "SOURCE_VERSION", "HEROKU_RELEASE_VERSION", "GIT_COMMIT"):
        value: Optional[str] = os.getenv(name)
        if value:
            return value
    return default

