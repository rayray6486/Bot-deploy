"""Minimal smoke tests for the Slum House Capital bot stack."""

from __future__ import annotations

import asyncio

from shc import config
from shc.llm import nemotron_client


async def main() -> None:
    config.load_env()
    config.ensure_runtime_config()
    summary = await nemotron_client.summarize_signals([])
    print("Nemotron summary:", summary)
    print("Runtime config keys:", list(config.runtime_config().keys()))


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())

