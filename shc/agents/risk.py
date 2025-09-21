"""Risk agent that evaluates alerts and surfaces cautionary notes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from . import hooks
from .. import rag


@dataclass
class RiskCheck:
    name: str
    status: str
    detail: str | None = None


@dataclass
class RiskContext:
    symbol: str
    setup_name: str
    timeframe: str
    checks: Sequence[RiskCheck] = field(default_factory=list)


class RiskAgent:
    """Summarise risk posture and append failure traps."""

    def build_alert_addendum(self, context: RiskContext) -> str:
        lines: List[str] = []
        for check in context.checks:
            base = f"{check.name}: {check.status}"
            if check.detail:
                base += f" ({check.detail})"
            lines.append(base)
        traps = hooks.failure_trap(context.symbol, context.setup_name)
        if traps:
            trap_lines = traps.splitlines()
            watch_text = " ".join(line.strip() for line in trap_lines)
            lines.append(f"Watch-outs: {watch_text}")
            source_line = rag.format_source_line(getattr(traps, "citations", []))
            if source_line:
                lines.append(source_line)
        return "\n".join(lines)
