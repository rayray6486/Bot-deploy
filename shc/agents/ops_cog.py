"""Operations controls."""

from __future__ import annotations

import logging
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import config, routing, state

LOGGER = logging.getLogger(__name__)

ops_group = app_commands.Group(name="ops", description="Operations commands")


class OpsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.tree.add_command(ops_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(ops_group.name, type=discord.AppCommandType.chat_input)

    @ops_group.command(name="status")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        statuses = list(state.all_statuses())
        lines = [
            f"Kill switch: {'ON' if state.kill_switch_enabled() else 'off'}",
            f"Global pause: {'ON' if state.is_global_pause() else 'off'}",
        ]
        for item in sorted(statuses, key=lambda s: s.name):
            last = item.last_success or item.last_run
            last_str = last.isoformat() if last else "n/a"
            error = f" ⚠️ {item.last_error}" if item.last_error else ""
            pause = " ⏸" if item.paused else ""
            lines.append(f"• {item.name}: {last_str}{pause}{error}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @ops_group.command(name="pause")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        state.set_global_pause(True)
        await interaction.response.send_message("Global pause enabled", ephemeral=True)

    @ops_group.command(name="resume")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        state.set_global_pause(False)
        await interaction.response.send_message("Global pause cleared", ephemeral=True)

    @ops_group.command(name="kill-switch")
    @app_commands.describe(mode="Turn the kill switch on or off")
    @app_commands.guild_only()
    async def kill_switch(self, interaction: discord.Interaction, mode: Literal["on", "off"]) -> None:
        enabled = mode == "on"
        state.set_kill_switch(enabled)
        await interaction.response.send_message(f"Kill switch {'enabled' if enabled else 'disabled'}", ephemeral=True)

    @ops_group.command(name="create-channel")
    @app_commands.describe(category="Existing category name", name="Channel name", kind="Channel type")
    @app_commands.guild_only()
    async def create_channel(self, interaction: discord.Interaction, category: str, name: str, kind: Literal["text", "voice"] = "text") -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("No guild context", ephemeral=True)
            return
        target_category = discord.utils.find(lambda c: c.name.lower() == category.lower(), guild.categories)
        if target_category is None:
            target_category = await guild.create_category(category, reason="Ops requested")
        channel: Optional[discord.abc.GuildChannel] = None
        if kind == "voice":
            channel = await guild.create_voice_channel(name, category=target_category, reason="Ops requested")
        else:
            channel = await guild.create_text_channel(name, category=target_category, reason="Ops requested")
        if isinstance(channel, discord.TextChannel):
            for key, channel_name in routing.CHANNEL_NAMES.items():
                if channel_name == channel.name:
                    config.set_channel_id(key, channel.id)
        await interaction.followup.send(f"Created {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}", ephemeral=True)

    @ops_group.command(name="archive")
    @app_commands.guild_only()
    async def archive(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        overwrites = channel.overwrites_for(channel.guild.default_role)
        overwrites.send_messages = False
        await channel.edit(name=f"archived-{channel.name}", overwrites={channel.guild.default_role: overwrites})
        await interaction.response.send_message(f"Archived {channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OpsCog(bot))

