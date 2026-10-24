import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import update_guild_config


class MasterRoleSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int) -> None:
        super().__init__(
            placeholder="Selecione o Cargo Master", min_values=1, max_values=1
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if (
            not interaction.guild
            or not interaction.user.guild_permissions.administrator
        ):
            return await interaction.response.send_message(
                "Apenas administradores podem alterar isso.", ephemeral=True
            )
        role = self.values[0]
        await update_guild_config(self.guild_id, master_role_id=role.id)
        await interaction.response.send_message(
            f"Cargo Master definido como {role.mention}.", ephemeral=True
        )


class MasterRoleView(discord.ui.View):
    def __init__(self, guild_id: int) -> None:
        super().__init__(timeout=120)
        self.add_item(MasterRoleSelect(guild_id))


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="setup", description="Configura o Cargo Master do servidor."
    )
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return await interaction.response.send_message(
                "Use este comando em um servidor.", ephemeral=True
            )
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Somente administradores podem configurar o Cargo Master.",
                ephemeral=True,
            )
        roles = [
            r for r in interaction.guild.roles if not r.is_default() and not r.managed
        ]
        if not roles:
            return await interaction.response.send_message(
                "Não há cargos disponíveis para selecionar.", ephemeral=True
            )
        await interaction.response.send_message(
            "Selecione o Cargo Master. Escolha um cargo de confiança com cuidado.",
            view=MasterRoleView(interaction.guild.id),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Setup(bot))
