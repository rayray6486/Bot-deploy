"""Helper hooks that connect agents to the shared RAG backend."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .. import rag


class AnswerText(str):
    """String subclass that carries citation metadata alongside text."""

    def __new__(cls, text: str, citations: Iterable[dict]):
        obj = super().__new__(cls, text)
        obj.citations = list(citations)
        return obj

    citations: list  # type: ignore[assignment]


@dataclass
class SetupContext:
    symbol: str
    setup_name: str
    timeframe: str
    key_levels: Sequence[float]

    def build_query(self) -> str:
        key_levels_str = ", ".join(f"{level:.2f}" for level in self.key_levels) if self.key_levels else ""
        return (
            f"{self.setup_name} entry/exit rules {self.timeframe} risk invalidation {self.symbol}"
            + (f" price levels {key_levels_str}" if key_levels_str else "")
        )


@dataclass
class TrapContext:
    symbol: str
    setup_name: str

    def build_query(self) -> str:
        return (
            f"{self.setup_name} common failure traps late entry thin liquidity exhaustion gaps {self.symbol}"
        )


def _to_answer_text(payload: dict, max_lines: int | None = None) -> AnswerText:
    text = (payload or {}).get("text", "")
    citations = (payload or {}).get("citations", [])
    if not text or text.strip().lower().startswith("no strong match"):
        return AnswerText("", [])
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
    final_text = "\n".join(lines)
    return AnswerText(final_text, citations)


def edu_justification(
    symbol: str, setup_name: str, timeframe: str, key_levels: Sequence[float]
) -> AnswerText:
    context = SetupContext(symbol=symbol, setup_name=setup_name, timeframe=timeframe, key_levels=key_levels)
    payload = rag.answer(context.build_query(), k=6, style="concise")
    return _to_answer_text(payload, max_lines=6)


def failure_trap(symbol: str, setup_name: str) -> AnswerText:
    context = TrapContext(symbol=symbol, setup_name=setup_name)
    payload = rag.answer(context.build_query(), k=4, style="bullets")
    text = _to_answer_text(payload, max_lines=2)
    if not text:
        return text
    lines = [line if line.startswith("-") else f"- {line}" for line in text.splitlines()]
    return AnswerText("\n".join(lines[:2]), text.citations)
