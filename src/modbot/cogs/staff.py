import discord
from discord import app_commands
from discord.ext import commands

from modbot.models import get_guild_config
from modbot.utils.permissions import require_master


class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="cargo", description="Adiciona ou remove um cargo de um membro."
    )
    @app_commands.describe(
        membro="Membro alvo",
        cargo="Cargo a alterar",
        acao="Adicionar ou remover",
        motivo="Motivo opcional",
    )
    @app_commands.choices(
        acao=[
            app_commands.Choice(name="Promover (adicionar cargo)", value="add"),
            app_commands.Choice(name="Rebaixar (remover cargo)", value="remove"),
        ]
    )
    async def cargo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        cargo: discord.Role,
        acao: app_commands.Choice[str],
        motivo: str = "Não informado",
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        me = interaction.guild.me
        if (
            cargo.is_default()
            or cargo.managed
            or cargo >= me.top_role
            or membro.top_role >= me.top_role
        ):
            return await interaction.response.send_message(
                "A hierarquia do bot não permite alterar esse cargo/membro.",
                ephemeral=True,
            )
        try:
            if acao.value == "add":
                await membro.add_roles(
                    cargo, reason=f"{interaction.user}: {motivo[:300]}"
                )
                verb = "adicionado a"
            else:
                await membro.remove_roles(
                    cargo, reason=f"{interaction.user}: {motivo[:300]}"
                )
                verb = "removido de"
            await interaction.response.send_message(
                f"Cargo {cargo.mention} {verb} {membro.mention}. Motivo: {motivo[:300]}"
            )
            config = await get_guild_config(interaction.guild.id)
            log = (
                interaction.guild.get_channel(config.staff_log_channel_id)
                if config.staff_log_channel_id
                else None
            )
            if isinstance(log, discord.TextChannel):
                await log.send(
                    f"🎖️ **Cargo alterado**\nResponsável: {interaction.user.mention}\nMembro: {membro.mention}\nCargo: {cargo.mention}\nAção: {acao.name}\nMotivo: {motivo[:300]}"
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar esse cargo.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Staff(bot))
