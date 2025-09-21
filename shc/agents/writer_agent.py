"""Writer agent responsible for building alert narratives."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from . import hooks
from .. import rag


@dataclass
class AlertData:
    symbol: str
    setup_name: str
    timeframe: str
    key_levels: Sequence[float] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: Sequence[str] = field(default_factory=list)


class WriterAgent:
    """Compose alert messages enriched with educational context."""

    def compose_alert(self, alert: AlertData) -> str:
        base_lines = self._base_lines(alert)
        justification = hooks.edu_justification(
            symbol=alert.symbol,
            setup_name=alert.setup_name,
            timeframe=alert.timeframe,
            key_levels=alert.key_levels,
        )
        if justification:
            base_lines.append("Why this setup:")
            base_lines.extend(self._indent_block(str(justification)))
            source_line = rag.format_source_line(getattr(justification, "citations", []))
            if source_line:
                base_lines.append(source_line)
        return "\n".join(base_lines)

    def _base_lines(self, alert: AlertData) -> List[str]:
        lines = [f"Symbol: {alert.symbol}", f"Setup: {alert.setup_name}", f"Timeframe: {alert.timeframe}"]
        if alert.key_levels:
            formatted_levels = ", ".join(f"{level:.2f}" for level in alert.key_levels)
            lines.append(f"Key levels: {formatted_levels}")
        for key, value in alert.metrics.items():
            lines.append(f"{key}: {value}")
        if alert.notes:
            lines.append("Notes:")
            lines.extend(self._indent_block("\n".join(alert.notes)))
        return lines

    @staticmethod
    def _indent_block(block: str) -> List[str]:
        if not block:
            return []
        return [f"  {line}" if line.strip() else "" for line in block.splitlines()]
