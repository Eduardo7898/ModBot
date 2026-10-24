import discord
from discord import app_commands
from discord.ext import commands

from src.models import get_guild_config, update_guild_config

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configura o Cargo Master do servidor.")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use este comando em um servidor.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Somente administradores podem configurar o Cargo Master.", ephemeral=True)
        roles = [r for r in interaction.guild.roles if not r.is_default() and not r.managed]
        if not roles:
            return await interaction.response.send_message("Não há cargos disponíveis para selecionar.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione o Cargo Master. Escolha um cargo de confiança com cuidado.",
            view=MasterRoleView(self.bot, interaction.guild.id, roles),
            ephemeral=True,
        )

class MasterRoleSelect(discord.ui.RoleSelect):
    def __init__(self, bot, guild_id):
        super().__init__(placeholder="Selecione o Cargo Master", min_values=1, max_values=1)
        self.bot, self.guild_id = bot, guild_id

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Apenas administradores podem alterar isso.", ephemeral=True)
        role = self.values[0]
        await update_guild_config(self.guild_id, master_role_id=role.id)
        await interaction.response.send_message(f"Cargo Master definido como {role.mention}.", ephemeral=True)

class MasterRoleView(discord.ui.View):
    def __init__(self, bot, guild_id, roles):
        super().__init__(timeout=120)
        self.add_item(MasterRoleSelect(bot, guild_id))

async def setup(bot):
    await bot.add_cog(Setup(bot))
