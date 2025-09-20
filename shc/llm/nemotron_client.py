"""Thin client for local Nemotron (Ollama) with optional OpenAI fallback."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Iterable, List

try:
    import aiohttp
except ModuleNotFoundError:  # pragma: no cover - fallback when dependency missing for local smoke tests
    aiohttp = None  # type: ignore

from .. import config

LOGGER = logging.getLogger(__name__)


def _build_prompt(signals: Iterable[Dict]) -> str:
    bullets = []
    for signal in signals:
        ticker = signal.get("ticker", "?")
        score = signal.get("score")
        rationale = signal.get("rationale", "")
        price = signal.get("price")
        risk = signal.get("risk", "balanced")
        parts = [f"Ticker: {ticker}"]
        if price is not None:
            parts.append(f"Price: {price:.2f}")
        if score is not None:
            parts.append(f"Score: {score:.2f}")
        if risk:
            parts.append(f"Risk: {risk}")
        if rationale:
            parts.append(f"Notes: {rationale}")
        bullets.append(" | ".join(parts))
    header = "You are the trading desk analyst for Slum House Capital. Summarise the incoming signals, highlight catalysts, and call out key risks in under 100 words."
    if not bullets:
        return header + " No actionable signals were provided."
    return header + "\n" + "\n".join(f"- {b}" for b in bullets)


async def summarize_signals(signals: List[Dict]) -> str:
    """Return a concise summary suitable for Discord alerts."""

    if not signals:
        return "No actionable signals right now."

    prompt = _build_prompt(signals)
    if aiohttp is not None:
        base_url = config.env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        model = config.env("NEMOTRON_MODEL", "nemotron-mini")
        timeout_value = config.env("NEMOTRON_TIMEOUT", "20")
        try:
            timeout = aiohttp.ClientTimeout(total=float(timeout_value))
        except (TypeError, ValueError):
            timeout = aiohttp.ClientTimeout(total=20)

        payload = {
            "model": model,
            "prompt": prompt,
            "options": {"temperature": 0.35, "top_p": 0.9},
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{base_url}/api/generate", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        text = data.get("response") or data.get("result")
                        if text:
                            return text.strip()
                        LOGGER.warning("Nemotron response missing text: %s", data)
                    else:
                        body = await response.text()
                        LOGGER.warning("Nemotron request failed (%s): %s", response.status, body)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            LOGGER.error("Nemotron request error: %s", exc)
    else:
        LOGGER.warning("aiohttp not installed; skipping Nemotron call")

    openai_key = config.env("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=openai_key)
            completion = await client.responses.create(
                model="gpt-4o-mini",
                input=prompt,
                max_output_tokens=200,
            )
            if completion.output and completion.output[0].get("content"):
                parts = completion.output[0]["content"]
                message = "".join(fragment.get("text", "") for fragment in parts if isinstance(fragment, dict))
                if message:
                    return message.strip()
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            LOGGER.error("OpenAI fallback failed: %s", exc)

    LOGGER.warning("Falling back to heuristic summary.")
    best = sorted(signals, key=lambda s: s.get("score", 0), reverse=True)[:3]
    parts = [f"{item.get('ticker', '?')}: score {item.get('score', 0):.2f}" for item in best]
    return "; ".join(parts) + " — monitor risk levels."


__all__ = ["summarize_signals"]

