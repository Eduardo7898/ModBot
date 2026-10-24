from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from modbot.utils.permissions import is_master


class Sync(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sync",
        description="Sincroniza os comandos de barra (Administrador ou Cargo Master).",
    )
    @app_commands.describe(
        escopo="Sincronizar apenas neste servidor (rápido) ou globalmente."
    )
    async def sync_commands(
        self,
        interaction: discord.Interaction,
        escopo: Literal["servidor_atual", "global"] = "servidor_atual",
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )

        if not (
            interaction.user.guild_permissions.administrator
            or await is_master(interaction)
        ):
            return await interaction.response.send_message(
                "Você precisa ser Administrador ou ter o Cargo Master.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        try:
            if escopo == "servidor_atual":
                self.bot.tree.copy_global_to(guild=interaction.guild)
                synced = await self.bot.tree.sync(guild=interaction.guild)
                await interaction.followup.send(
                    f"✅ {len(synced)} comandos sincronizados neste servidor!"
                )
            else:
                synced = await self.bot.tree.sync()
                await interaction.followup.send(
                    f"🌐 {len(synced)} comandos sincronizados globalmente! "
                    "(Pode levar alguns minutos para propagar)."
                )
        except Exception as exc:
            await interaction.followup.send(f"❌ Falha ao sincronizar: {exc}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Sync(bot))
