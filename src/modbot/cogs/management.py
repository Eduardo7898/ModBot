import discord
from discord import app_commands
from discord.ext import commands

from modbot.models import get_guild_config, update_guild_config
from modbot.utils.permissions import require_master


class Management(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="gerenciamento",
        description="Mostra o painel administrativo e métricas do bot.",
    )
    async def gerenciamento(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        config = await get_guild_config(interaction.guild.id)
        embed = discord.Embed(
            title="Painel de gerenciamento", color=discord.Color.blurple()
        )
        embed.add_field(
            name="Latência", value=f"{self.bot.latency * 1000:.0f} ms", inline=True
        )
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(
            name="Membros em cache",
            value=str(sum(g.member_count or 0 for g in self.bot.guilds)),
            inline=True,
        )
        embed.add_field(
            name="Memória do processo",
            value="Indisponível no Android/Termux",
            inline=True,
        )
        embed.add_field(
            name="Cargo Master",
            value=f"<@&{config.master_role_id}>"
            if config.master_role_id
            else "Não configurado",
            inline=True,
        )
        embed.add_field(
            name="Proteção Anti-Raid",
            value="Ativada" if config.raid_protection_enabled else "Desativada",
            inline=True,
        )
        await interaction.response.send_message(
            embed=embed, view=ConfigPanel(), ephemeral=True
        )


class ConfigPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Configurar boas-vindas", style=discord.ButtonStyle.primary, emoji="👋"
    )
    async def welcome(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not await require_master(interaction):
            return
        await interaction.response.send_message(
            "Use `/config_canal` para configurar os canais.", ephemeral=True
        )


class ConfigChannel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="config_canal", description="Configura um canal do bot.")
    @app_commands.describe(tipo="Qual função terá o canal", canal="Canal de destino")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Boas-vindas", value="welcome_channel_id"),
            app_commands.Choice(name="Saídas", value="leave_channel_id"),
            app_commands.Choice(name="Anti-Raid", value="antiraid_channel_id"),
            app_commands.Choice(name="Logs de voz", value="call_log_channel_id"),
            app_commands.Choice(name="Logs da equipe", value="staff_log_channel_id"),
            app_commands.Choice(name="Logs de tickets", value="ticket_log_channel_id"),
        ]
    )
    async def config_canal(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        canal: discord.TextChannel,
    ):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        await update_guild_config(interaction.guild.id, **{tipo.value: canal.id})
        await interaction.response.send_message(
            f"Canal de {tipo.name} definido para {canal.mention}.", ephemeral=True
        )

    @app_commands.command(
        name="config_tickets",
        description="Configura categoria e cargo de suporte dos tickets.",
    )
    async def config_tickets(
        self,
        interaction: discord.Interaction,
        categoria: discord.CategoryChannel,
        cargo_suporte: discord.Role,
    ):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        await update_guild_config(
            interaction.guild.id,
            ticket_category_id=categoria.id,
            ticket_support_role_id=cargo_suporte.id,
        )
        await interaction.response.send_message(
            f"Tickets configurados. Categoria: **{categoria.name}**; suporte: {cargo_suporte.mention}.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Management(bot))
    await bot.add_cog(ConfigChannel(bot))
