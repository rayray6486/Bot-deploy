"""Discord cog exposing RAG-powered education commands."""
from __future__ import annotations

import os
from typing import List, Optional

import discord
from discord.abc import Messageable
from discord import app_commands
from discord.ext import commands

from .. import rag


MAX_DISCORD_MESSAGE = 1900


def _append_sources(text: str, citations: List[dict]) -> str:
    source_line = rag.format_source_line(citations)
    if not source_line:
        return text
    if source_line in text:
        return text
    return f"{text}\n{source_line}" if "\n" in text else f"{text} {source_line}"


def _trim_text(text: str, max_lines: Optional[int] = None) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
    message = "\n".join(lines)
    if len(message) > MAX_DISCORD_MESSAGE:
        return message[: MAX_DISCORD_MESSAGE - 1] + "…"
    return message


class _ChunkButton(discord.ui.Button):
    def __init__(self, chunk: rag.Chunk, index: int):
        super().__init__(label=f"View {index}", style=discord.ButtonStyle.secondary)
        self.chunk = chunk

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        preview = self.chunk.text.strip()
        if len(preview) > MAX_DISCORD_MESSAGE:
            preview = preview[: MAX_DISCORD_MESSAGE - 1] + "…"
        await interaction.response.send_message(
            f"{self.chunk.label}\n{preview}", ephemeral=True
        )


class LearnView(discord.ui.View):
    def __init__(self, chunks: List[rag.Chunk]):
        super().__init__(timeout=180)
        for idx, chunk in enumerate(chunks, start=1):
            self.add_item(_ChunkButton(chunk, idx))


class EducationCog(commands.Cog):
    learn = app_commands.Group(name="learn", description="SHC learning tools")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.learn_channel_id = int(os.getenv("LEARN_CHANNEL_ID", "0") or 0)
        if not self.bot.tree.get_command(self.learn.name):
            self.bot.tree.add_command(self.learn)

    def cog_unload(self) -> None:
        try:
            self.bot.tree.remove_command(self.learn.name, type=self.learn.type)
        except Exception:
            pass

    async def _respond(
        self,
        interaction: discord.Interaction,
        *,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        view: Optional[discord.ui.View] = None,
        ephemeral: bool = False,
    ) -> None:
        target = None
        if not ephemeral and self.learn_channel_id:
            channel = self.bot.get_channel(self.learn_channel_id)
            if isinstance(channel, Messageable) and interaction.channel_id != self.learn_channel_id:
                target = channel
        if target is not None:
            await target.send(content=content, embed=embed, view=view)
            await interaction.followup.send(
                f"Shared in <#{self.learn_channel_id}>", ephemeral=True
            )
        else:
            await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)

    @app_commands.command(name="ask", description="Ask the SHC playbook a trading question")
    @app_commands.describe(question="What would you like to learn?")
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer(thinking=True)
        result = rag.answer(question, k=6, style="concise")
        text = result.get("text", "No strong match")
        if text.lower().startswith("no strong match"):
            await interaction.followup.send("No strong match", ephemeral=True)
            return
        message = _append_sources(text, result.get("citations", []))
        message = _trim_text(message, max_lines=10)
        await self._respond(interaction, content=message)

    @learn.command(name="search", description="Search the SHC knowledge base")
    @app_commands.describe(query="Topic to search")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True)
        hits = rag.search(query, k=5)
        if not hits:
            await interaction.followup.send("No strong match", ephemeral=True)
            return
        embed = discord.Embed(title=f'Search results for "{query}"', colour=discord.Colour.blurple())
        for idx, chunk in enumerate(hits, start=1):
            embed.add_field(
                name=f"{idx}. {chunk.shortname} §{chunk.chunk + 1}",
                value=f"{chunk.snippet}\n{chunk.label}",
                inline=False,
            )
        view = LearnView(hits)
        await self._respond(interaction, embed=embed, view=view)

    @app_commands.command(name="explain_signal", description="Explain a trading signal with SHC knowledge")
    @app_commands.describe(ticker="Ticker symbol", setup="Setup name", timeframe="Optional timeframe")
    async def explain_signal(
        self,
        interaction: discord.Interaction,
        ticker: str,
        setup: str,
        timeframe: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        timeframe_label = timeframe or "multi-timeframe"
        query = (
            f"{setup} thesis entry invalidation risk note traps {ticker} timeframe {timeframe_label}"
        )
        result = rag.answer(query, k=6, style="explainer")
        text = result.get("text", "No strong match")
        if text.lower().startswith("no strong match"):
            await interaction.followup.send("No strong match", ephemeral=True)
            return
        message = _append_sources(text, result.get("citations", []))
        message = _trim_text(message, max_lines=12)
        await self._respond(interaction, content=message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EducationCog(bot))
