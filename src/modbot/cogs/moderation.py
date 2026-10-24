import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import update_guild_config
from modbot.utils.permissions import is_master, require_master


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="protecao",
        description="Ativa ou desativa a contenção conservadora de novos bots.",
    )
    @app_commands.describe(ativada="Se a proteção deve ficar ativada.")
    async def protecao(self, interaction: discord.Interaction, ativada: bool) -> None:
        if not interaction.guild:
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        await update_guild_config(interaction.guild.id, raid_protection_enabled=ativada)
        await interaction.response.send_message(
            f"Proteção de novos bots {'ativada' if ativada else 'desativada'}. "
            "A proteção não remove cargos de usuários automaticamente.",
            ephemeral=True,
        )

    @app_commands.command(name="expulsar", description="Expulsa um membro do servidor.")
    @app_commands.describe(membro="Membro a expulsar", motivo="Motivo da expulsão")
    @app_commands.default_permissions(kick_members=True)
    async def expulsar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: str = "Não informado",
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not (
            interaction.user.guild_permissions.kick_members
            or await is_master(interaction)
        ):
            return await interaction.response.send_message(
                "Você não tem permissão para expulsar.", ephemeral=True
            )
        if (
            membro.id == interaction.guild.owner_id
            or membro.top_role >= interaction.guild.me.top_role
        ):
            return await interaction.response.send_message(
                "Não posso expulsar esse membro devido à hierarquia de cargos.",
                ephemeral=True,
            )
        try:
            await membro.kick(
                reason=f"{interaction.user} ({interaction.user.id}): {motivo[:400]}"
            )
            await interaction.response.send_message(
                f"{membro} foi expulso. Motivo: {motivo[:400]}", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para expulsar esse membro.", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
