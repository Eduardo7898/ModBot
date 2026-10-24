import discord
from discord import app_commands
from discord.ext import commands

from modbot.models import get_guild_config
from modbot.utils.permissions import require_master

TICKET_TYPES = [
    discord.SelectOption(label="Dúvidas", value="duvidas", emoji="❓"),
    discord.SelectOption(label="Denúncias", value="denuncias", emoji="🛡️"),
    discord.SelectOption(label="Compras", value="compras", emoji="🛒"),
]


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Selecione a categoria do ticket",
            min_values=1,
            max_values=1,
            options=TICKET_TYPES,
            custom_id="tickets:categoria",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        config = await get_guild_config(guild.id)
        category = (
            guild.get_channel(config.ticket_category_id)
            if config.ticket_category_id
            else None
        )
        support_role = (
            guild.get_role(config.ticket_support_role_id)
            if config.ticket_support_role_id
            else None
        )
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.response.send_message(
                "A categoria de tickets ainda não foi configurada.", ephemeral=True
            )
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        safe_name = (
            "".join(
                c.lower() if c.isalnum() or c == "-" else "-"
                for c in interaction.user.display_name
            )[:35].strip("-")
            or "membro"
        )
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{self.values[0]}-{safe_name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket de {interaction.user} ({interaction.user.id}) | categoria: {self.values[0]}",
                reason=f"Ticket aberto por {interaction.user} ({interaction.user.id})",
            )
            view = TicketControls(interaction.user.id, config.ticket_support_role_id)
            mention = f"<@&{support_role.id}> " if support_role else ""
            await channel.send(
                f"{interaction.user.mention} {mention}Seu ticket foi aberto. Explique como podemos ajudar.",
                embed=discord.Embed(
                    title=f"Ticket: {self.values[0].title()}",
                    color=discord.Color.blurple(),
                ),
                view=view,
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=bool(support_role), everyone=False
                ),
            )
            await interaction.response.send_message(
                f"Ticket criado: {channel.mention}", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para criar canais. Verifique Manage Channels.",
                ephemeral=True,
            )


class TicketControls(discord.ui.View):
    def __init__(self, opener_id: int, support_role_id: int | None):
        super().__init__(timeout=None)
        self.opener_id = opener_id
        self.support_role_id = support_role_id

    @discord.ui.button(
        label="Fechar ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket:close",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        is_support = interaction.user.guild_permissions.manage_channels or (
            self.support_role_id
            and any(r.id == self.support_role_id for r in interaction.user.roles)
        )
        if interaction.user.id != self.opener_id and not is_support:
            return await interaction.response.send_message(
                "Somente quem abriu ou a equipe de suporte pode fechar.", ephemeral=True
            )
        await interaction.response.send_message(
            "Ticket será fechado em 5 segundos.", ephemeral=True
        )
        import asyncio

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(
                reason=f"Ticket fechado por {interaction.user} ({interaction.user.id})"
            )
        except discord.HTTPException:
            pass

    @discord.ui.button(
        label="Adicionar membro",
        style=discord.ButtonStyle.secondary,
        emoji="➕",
        custom_id="ticket:add_member",
    )
    async def add_member(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        is_support = interaction.user.guild_permissions.manage_channels or (
            self.support_role_id
            and any(r.id == self.support_role_id for r in interaction.user.roles)
        )
        if interaction.user.id != self.opener_id and not is_support:
            return await interaction.response.send_message(
                "Somente quem abriu ou a equipe de suporte pode adicionar membros.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            "Use /ticket_adicionar neste canal para conceder acesso ao membro.",
            ephemeral=True,
        )


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketPanel())

    @app_commands.command(
        name="ticket_painel", description="Publica o painel para abrir tickets."
    )
    async def ticket_painel(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        await interaction.response.send_message(
            "Precisa de ajuda? Selecione uma categoria abaixo.",
            view=TicketPanel(),
        )

    @app_commands.command(
        name="ticket_adicionar", description="Adiciona um membro ao ticket atual."
    )
    async def ticket_adicionar(
        self, interaction: discord.Interaction, membro: discord.Member
    ):
        if not interaction.guild or not isinstance(
            interaction.channel, discord.TextChannel
        ):
            return await interaction.response.send_message(
                "Use dentro de um canal de ticket.", ephemeral=True
            )
        config = await get_guild_config(interaction.guild.id)
        is_support = interaction.user.guild_permissions.manage_channels or (
            isinstance(interaction.user, discord.Member)
            and config.ticket_support_role_id
            and any(
                r.id == config.ticket_support_role_id for r in interaction.user.roles
            )
        )
        if not is_support and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Somente a equipe de suporte pode usar este comando.", ephemeral=True
            )
        await interaction.channel.set_permissions(
            membro, view_channel=True, send_messages=True, read_message_history=True
        )
        await interaction.response.send_message(
            f"{membro.mention} recebeu acesso ao ticket.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
