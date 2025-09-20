"""Bootstrap utilities for initial guild setup."""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from . import config

LOGGER = logging.getLogger(__name__)

bootstrap_group = app_commands.Group(name="bootstrap", description="Bootstrap guild resources")

ROLE_NAMES = ["Admin", "Analyst", "Member", "Muted"]
CATEGORY_STRUCTURE: Dict[str, List[Tuple[str, str, str]]] = {
    "Signals": [
        ("alerts-day-trade", "text", "alerts_day_trade"),
        ("alerts-swing", "text", "alerts_swing"),
        ("alerts-leaps", "text", "alerts_leaps"),
        ("alerts-longterm", "text", "alerts_longterm"),
    ],
    "Market Data": [
        ("market-open", "text", "market_open"),
        ("market-close", "text", "market_close"),
        ("news-wire", "text", "news_wire"),
        ("ticker-requests", "text", "ticker_requests"),
    ],
    "Ops": [
        ("ops-console", "text", "ops_console"),
        ("moderation-log", "text", "moderation_log"),
        ("heartbeat", "text", "heartbeat"),
    ],
    "General": [
        ("welcome", "text", "welcome"),
        ("faq", "text", "faq"),
        ("house-rules", "text", "house_rules"),
    ],
}

WEBHOOK_CHANNEL_KEYS = ["alerts_day_trade", "alerts_swing", "alerts_leaps", "alerts_longterm"]


class BootstrapCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.tree.add_command(bootstrap_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(bootstrap_group.name, type=discord.AppCommandType.chat_input)

    @bootstrap_group.command(name="full")
    @app_commands.guild_only()
    async def full(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This command must be run inside a guild", ephemeral=True)
            return
        config.set_guild(guild.id)
        role_summary = await self._ensure_roles(guild)
        category_summary = await self._ensure_categories(guild)
        webhook_summary = await self._ensure_webhooks(guild)
        message = "\n".join(role_summary + category_summary + webhook_summary)
        await interaction.followup.send(message or "Bootstrap complete", ephemeral=True)

    @bootstrap_group.command(name="roles")
    @app_commands.guild_only()
    async def roles(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("No guild context", ephemeral=True)
            return
        summary = await self._ensure_roles(guild)
        await interaction.followup.send("\n".join(summary), ephemeral=True)

    @bootstrap_group.command(name="channels")
    @app_commands.guild_only()
    async def channels(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("No guild context", ephemeral=True)
            return
        summary = await self._ensure_categories(guild)
        await interaction.followup.send("\n".join(summary), ephemeral=True)

    @bootstrap_group.command(name="webhooks")
    @app_commands.guild_only()
    async def webhooks(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("No guild context", ephemeral=True)
            return
        summary = await self._ensure_webhooks(guild)
        await interaction.followup.send("\n".join(summary), ephemeral=True)

    async def _ensure_roles(self, guild: discord.Guild) -> List[str]:
        summaries = []
        existing = {role.name.lower(): role for role in guild.roles}
        for name in ROLE_NAMES:
            role = existing.get(name.lower())
            if role is None:
                role = await guild.create_role(name=name, reason="Bootstrap roles")
                summaries.append(f"Created role {name}")
            else:
                summaries.append(f"Role exists {name}")
            config.set_role_id(name.lower(), role.id)
        return summaries

    async def _ensure_categories(self, guild: discord.Guild) -> List[str]:
        summaries: List[str] = []
        for category_name, channels in CATEGORY_STRUCTURE.items():
            category = discord.utils.find(lambda c: c.name.lower() == category_name.lower(), guild.categories)
            if category is None:
                category = await guild.create_category(category_name, reason="Bootstrap categories")
                summaries.append(f"Created category {category_name}")
            else:
                summaries.append(f"Category exists {category_name}")
            for channel_name, kind, key in channels:
                channel = discord.utils.find(lambda ch: ch.name == channel_name, category.channels)
                if channel is None:
                    if kind == "voice":
                        channel = await guild.create_voice_channel(channel_name, category=category, reason="Bootstrap channel")
                    else:
                        channel = await guild.create_text_channel(channel_name, category=category, reason="Bootstrap channel")
                    summaries.append(f"Created channel {channel_name}")
                else:
                    summaries.append(f"Channel exists {channel_name}")
                if isinstance(channel, discord.TextChannel):
                    config.set_channel_id(key, channel.id)
        return summaries

    async def _ensure_webhooks(self, guild: discord.Guild) -> List[str]:
        summaries: List[str] = []
        for key in WEBHOOK_CHANNEL_KEYS:
            channel_id = config.channel_id(key)
            if not channel_id:
                summaries.append(f"No channel id for {key}")
                continue
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                summaries.append(f"Channel not found for {key}")
                continue
            webhook = await self._ensure_channel_webhook(channel)
            if webhook:
                config.set_webhook_url(key, webhook.url)
                summaries.append(f"Webhook ready for {channel.name}")
        return summaries

    async def _ensure_channel_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        try:
            webhooks = await channel.webhooks()
        except discord.HTTPException as exc:
            LOGGER.error("Failed to list webhooks for %s: %s", channel, exc)
            return None
        for webhook in webhooks:
            if webhook.name.startswith("SHC"):
                return webhook
        try:
            return await channel.create_webhook(name=f"SHC {channel.name}", reason="Bootstrap webhooks")
        except discord.HTTPException as exc:
            LOGGER.error("Failed to create webhook for %s: %s", channel, exc)
            return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BootstrapCog(bot))

