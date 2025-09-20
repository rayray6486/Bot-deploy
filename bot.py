"""Entry point for the Slum House Capital Discord bot."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import discord
from discord.ext import commands

from shc import config

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

INITIAL_EXTENSIONS: List[str] = [
    "shc.bootstrap_cog",
    "shc.agents.signals_cog",
    "shc.agents.news_cog",
    "shc.agents.scheduler_cog",
    "shc.agents.ops_cog",
]


class SHCBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        config.ensure_runtime_config()
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                logging.info("Loaded extension %s", extension)
            except Exception as exc:  # pragma: no cover - defensive at runtime
                logging.exception("Failed to load extension %s: %s", extension, exc)
        guild_id = config.guild()
        try:
            if guild_id:
                guild = discord.Object(id=guild_id)
                await self.tree.sync(guild=guild)
                logging.info("Slash commands synced for guild %s", guild_id)
            else:
                await self.tree.sync()
                logging.info("Slash commands synced globally")
        except discord.HTTPException as exc:
            logging.error("Command sync failed: %s", exc)

    async def on_ready(self) -> None:
        guild_id = config.guild()
        loaded = ", ".join(INITIAL_EXTENSIONS)
        logging.info("Ready as %s (guild=%s). Extensions: %s", self.user, guild_id, loaded)


def main() -> None:
    config.load_env(Path(".env") if Path(".env").exists() else None)
    config.ensure_runtime_config()
    token = config.bot_token()
    bot = SHCBot()
    bot.run(token)


if __name__ == "__main__":  # pragma: no cover
    main()

