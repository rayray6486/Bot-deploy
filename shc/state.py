"""Shared agent state and health tracking for Slum House Capital."""

from __future__ import annotations

import dataclasses
import datetime as dt
import threading
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional


@dataclasses.dataclass
class AgentStatus:
    name: str
    last_run: Optional[dt.datetime] = None
    last_success: Optional[dt.datetime] = None
    last_error: Optional[str] = None
    paused: bool = False
    details: Dict[str, str] = dataclasses.field(default_factory=dict)

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "last_run": _fmt_dt(self.last_run),
            "last_success": _fmt_dt(self.last_success),
            "last_error": self.last_error,
            "paused": str(self.paused),
            **self.details,
        }


@dataclasses.dataclass
class SignalRecord:
    ticker: str
    mode: str
    price: float
    timestamp: dt.datetime
    meta: Dict[str, str] = dataclasses.field(default_factory=dict)


_STATUSES: Dict[str, AgentStatus] = {}
_SIGNALS: Deque[SignalRecord] = deque(maxlen=250)
_LOCK = threading.Lock()
_GLOBAL_PAUSE = False
_KILL_SWITCH = False


def _fmt_dt(value: Optional[dt.datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.replace(microsecond=0, tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def mark_run(name: str, *, success: bool = True, error: Optional[str] = None, details: Optional[Dict[str, str]] = None) -> AgentStatus:
    now = dt.datetime.utcnow()
    with _LOCK:
        status = _STATUSES.setdefault(name, AgentStatus(name=name))
        status.last_run = now
        if success:
            status.last_success = now
            status.last_error = None
        elif error:
            status.last_error = error
        if details:
            status.details.update(details)
        return status


def mark_error(name: str, error: str) -> AgentStatus:
    return mark_run(name, success=False, error=error)


def set_agent_paused(name: str, paused: bool) -> AgentStatus:
    with _LOCK:
        status = _STATUSES.setdefault(name, AgentStatus(name=name))
        status.paused = paused
        return status


def agent_status(name: str) -> AgentStatus:
    with _LOCK:
        return _STATUSES.setdefault(name, AgentStatus(name=name))


def all_statuses() -> Iterable[AgentStatus]:
    with _LOCK:
        return list(_STATUSES.values())


def record_signal(ticker: str, *, mode: str, price: float, meta: Optional[Dict[str, str]] = None) -> None:
    now = dt.datetime.utcnow()
    with _LOCK:
        _SIGNALS.append(SignalRecord(ticker=ticker.upper(), mode=mode, price=price, timestamp=now, meta=meta or {}))


def recent_signals(hours: float = 8) -> List[SignalRecord]:
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=hours)
    with _LOCK:
        return [record for record in list(_SIGNALS) if record.timestamp >= cutoff]


def set_global_pause(paused: bool) -> None:
    global _GLOBAL_PAUSE
    with _LOCK:
        _GLOBAL_PAUSE = paused


def is_global_pause() -> bool:
    with _LOCK:
        return _GLOBAL_PAUSE


def set_kill_switch(enabled: bool) -> None:
    global _KILL_SWITCH
    with _LOCK:
        _KILL_SWITCH = enabled


def kill_switch_enabled() -> bool:
    with _LOCK:
        return _KILL_SWITCH


__all__ = [
    "AgentStatus",
    "agent_status",
    "all_statuses",
    "is_global_pause",
    "kill_switch_enabled",
    "mark_error",
    "mark_run",
    "record_signal",
    "recent_signals",
    "set_agent_paused",
    "set_global_pause",
    "set_kill_switch",
]

