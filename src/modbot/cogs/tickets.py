import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import get_guild_config, update_guild_config  # Certifique-se de ter uma função de update no seu model
from modbot.utils.permissions import require_master

TICKET_TYPES = [
    discord.SelectOption(label="Dúvidas", value="duvidas", emoji="❓", description="Esclarecimentos e orientações"),
    discord.SelectOption(label="Denúncias", value="denuncias", emoji="🛡️", description="Reporto de players ou violações"),
    discord.SelectOption(label="Compras", value="compras", emoji="🛒", description="Aquisição de produtos/VIP"),
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
                topic=(
                    f"Ticket de {interaction.user} ({interaction.user.id}) | "
                    f"categoria: {self.values[0]}"
                ),
                reason=f"Ticket aberto por {interaction.user} ({interaction.user.id})",
            )
            view = TicketControls(interaction.user.id, config.ticket_support_role_id)
            mention = f"<@&{support_role.id}> " if support_role else ""
            welcome_msg = (
                f"{interaction.user.mention} {mention}"
                "Seu ticket foi aberto. Explique como podemos ajudar."
            )
            await channel.send(
                welcome_msg,
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
    def __init__(self, opener_id: int | None = None, support_role_id: int | None = None):
        super().__init__(timeout=None)
        self.opener_id = opener_id
        self.support_role_id = support_role_id

    async def _resolve_permissions(self, interaction: discord.Interaction) -> tuple[bool, int | None]:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False, None

        opener_id = self.opener_id
        if opener_id is None and interaction.channel and interaction.channel.topic:
            match = re.search(r"\((\d{17,20})\)", interaction.channel.topic)
            if match:
                opener_id = int(match.group(1))

        support_role_id = self.support_role_id
        if support_role_id is None:
            config = await get_guild_config(interaction.guild.id)
            support_role_id = config.ticket_support_role_id

        is_support = (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.administrator
            or (support_role_id and any(r.id == support_role_id for r in interaction.user.roles))
        )
        is_opener = opener_id is not None and interaction.user.id == opener_id
        return is_support or is_opener, opener_id

    @discord.ui.button(label="Fechar ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_access, _ = await self._resolve_permissions(interaction)
        if not has_access:
            return await interaction.response.send_message("Somente quem abriu ou a equipe de suporte pode fechar.", ephemeral=True)

        await interaction.response.send_message("Ticket será fechado em 5 segundos.", ephemeral=True)
        await asyncio.sleep(5)
        try:
            if isinstance(interaction.channel, discord.TextChannel):
                await interaction.channel.delete(reason=f"Ticket fechado por {interaction.user} ({interaction.user.id})")
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Adicionar membro", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="ticket:add_member")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_access, _ = await self._resolve_permissions(interaction)
        if not has_access:
            return await interaction.response.send_message("Somente quem abriu ou a equipe de suporte pode adicionar membros.", ephemeral=True)
        await interaction.response.send_message("Use /ticket_adicionar neste canal para conceder acesso ao membro.", ephemeral=True)


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketPanel())
        self.bot.add_view(TicketControls())

    async def build_panel_embed(self, guild_id: int) -> discord.Embed:
        """Constrói o embed dinâmico com base nas configurações salvas no banco de dados."""
        config = await get_guild_config(guild_id)
        
        # Valores padrão caso não estejam salvos no banco
        title = getattr(config, "ticket_panel_title", "🛠️ CENTRAL DE ATENDIMENTO")
        description = getattr(
            config, 
            "ticket_panel_desc", 
            "Bem-vindo à Central de Suporte!\nSelecione a categoria abaixo para abrir um ticket."
        )
        color_int = getattr(config, "ticket_panel_color", discord.Color.blurple().value)
        
        embed = discord.Embed(title=title, description=description, color=color_int)
        
        # Campos opcionais baseados no painel estilo Ticket King
        footer_text = getattr(config, "ticket_panel_footer", "Sistema de Tickets • Todos os direitos reservados.")
        footer_icon = getattr(config, "ticket_panel_footer_icon", None)
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=footer_icon)
            
        image_url = getattr(config, "ticket_panel_image", None)
        if image_url:
            embed.set_image(url=image_url)
            
        thumbnail_url = getattr(config, "ticket_panel_thumbnail", None)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
            
        return embed

    @app_commands.command(name="ticket_painel", description="Publica o painel customizado para abrir tickets.")
    async def ticket_painel(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return
            
        embed = await self.build_panel_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=TicketPanel())

    @app_commands.command(name="ticket_config_painel", description="Personaliza a aparência do painel de tickets.")
    @app_commands.describe(
        titulo="Título do Embed",
        descricao="Descrição do Embed",
        cor="Cor em hexadecimal (ex: #FFD700)",
        imagem_url="URL da imagem grande do embed",
        rodape="Texto do rodapé"
    )
    async def ticket_config_painel(
        self, 
        interaction: discord.Interaction, 
        titulo: str = None, 
        descricao: str = None, 
        cor: str = None, 
        imagem_url: str = None, 
        rodape: str = None
    ):
        if not interaction.guild or not await require_master(interaction):
            return

        # Converte a cor hexadecimal para inteiro se fornecida
        color_value = None
        if cor:
            try:
                clean_hex = cor.lstrip("#")
                color_value = int(clean_hex, 16)
            except ValueError:
                return await interaction.response.send_message("Cor inválida! Use formato HEX (ex: #FFD700).", ephemeral=True)

        # Monta um dicionário com os campos preenchidos para salvar no DB
        updates = {}
        if titulo: updates["ticket_panel_title"] = titulo
        if descricao: updates["ticket_panel_desc"] = descricao
        if color_value is not None: updates["ticket_panel_color"] = color_value
        if imagem_url: updates["ticket_panel_image"] = imagem_url
        if rodape: updates["ticket_panel_footer"] = rodape

        # Salva no banco de dados (certifique-se de adaptar para o método do seu ORM/DB)
        await update_guild_config(interaction.guild.id, **updates)

        await interaction.response.send_message("✅ Configurações do painel atualizadas com sucesso! Use `/ticket_painel` para republicar.", ephemeral=True)

    @app_commands.command(name="ticket_adicionar", description="Adiciona um membro ao ticket atual.")
    async def ticket_adicionar(self, interaction: discord.Interaction, membro: discord.Member):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use dentro de um canal de ticket.", ephemeral=True)
            
        config = await get_guild_config(interaction.guild.id)
        is_support = interaction.user.guild_permissions.manage_channels or (
            isinstance(interaction.user, discord.Member)
            and config.ticket_support_role_id
            and any(r.id == config.ticket_support_role_id for r in interaction.user.roles)
        )
        if not is_support and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Somente a equipe de suporte pode usar este comando.", ephemeral=True)
            
        await interaction.channel.set_permissions(membro, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"{membro.mention} recebeu acesso ao ticket.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tickets(bot))