"""Administration and operational slash commands."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import subprocess
from typing import Iterable, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from slum import get_version
from slum.alerts import ENVIRONMENT_OVERRIDES, CHANNEL_KEYS, configure as configure_router, update_channel


def _coerce_admin_id(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed or None


ADMIN_USER_ID = _coerce_admin_id(os.getenv("ADMIN_USER_ID"))
CHANNEL_CHOICES = [
    app_commands.Choice(name=key.replace("_", " ").title(), value=key) for key in CHANNEL_KEYS
]


class AdminCog(commands.Cog):
    """Administrative helpers for guild owners."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        configure_router(bot)
        self.started_at = dt.datetime.now(dt.timezone.utc)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                await ch.send(
                    "👋 Slum House Capital bot installed. Use `/set_channel` in the channel you want alerts."
                )
                break

    @app_commands.command(name="ping", description="Check whether the bot is responsive.")
    async def ping(self, interaction: Interaction) -> None:
        latency_ms = (self.bot.latency or 0.0) * 1000
        await interaction.response.send_message(f"🏓 Pong! {latency_ms:.0f} ms", ephemeral=True)

    @app_commands.command(name="health", description="Display version, uptime, and recent journal entries.")
    async def health(self, interaction: Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        version = get_version()
        uptime = self._format_timedelta(dt.datetime.now(dt.timezone.utc) - self.started_at)
        journal = await self._fetch_journal_lines()
        journal_block = f"```{journal}```" if journal else "`journalctl` not available"
        message = f"**Version:** {version}\n**Uptime:** {uptime}\n\n**journalctl**\n{journal_block}"
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(name="set_channel", description="Map an alert type to a channel.")
    @app_commands.describe(channel="Channel that should receive the alert type")
    @app_commands.choices(key=CHANNEL_CHOICES)
    async def set_channel(
        self, interaction: Interaction, key: app_commands.Choice[str], channel: discord.TextChannel
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        config = update_channel(key.value, channel.id)
        env_override = ENVIRONMENT_OVERRIDES.get(key.value)
        override_note = ""
        if env_override and os.getenv(env_override):
            override_note = f"\n⚠️ Environment variable `{env_override}` overrides this mapping."
        await interaction.followup.send(
            f"Saved `{key.value}` → {channel.mention}.{override_note}\nEffective channel ID: `{config.get(key.value)}`",
            ephemeral=True,
        )

    def _is_admin(self, interaction: Interaction) -> bool:
        if ADMIN_USER_ID and interaction.user.id == ADMIN_USER_ID:
            return True
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        if member and member.guild_permissions.administrator:
            return True
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            return True
        return False

    async def _fetch_journal_lines(self) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_journal)

    @staticmethod
    def _read_journal() -> str:
        command = ["journalctl", "-u", "slumhousebot", "-n", "20", "--no-pager"]
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
        except FileNotFoundError:
            return ""
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            return ""
        lines = output.splitlines()[-20:]
        trimmed = _trim_to_limit(lines, 1800)
        return trimmed

    @staticmethod
    def _format_timedelta(delta: dt.timedelta) -> str:
        total = int(delta.total_seconds())
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if days or hours:
            parts.append(f"{hours}h")
        if days or hours or minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return " ".join(parts)


def _trim_to_limit(lines: Iterable[str], limit: int) -> str:
    collected: list[str] = []
    length = 0
    for line in lines:
        line_length = len(line) + 1  # include newline
        if length + line_length > limit:
            break
        collected.append(line)
        length += line_length
    return "\n".join(collected)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

