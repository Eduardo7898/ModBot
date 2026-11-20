from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from modbot.cogs.tickets import (
    PublishPanelModal,
    TICKET_TYPES,
    _parse_id,
    get_runtime_settings,
    set_ticket_type_category,
)
from modbot.database.models import get_guild_config, update_guild_config
from modbot.utils.permissions import require_master

CHANNEL_ITEMS = [
    ("Boas-vindas", "welcome_channel_id", "👋"),
    ("Saídas", "leave_channel_id", "🚪"),
    ("Anti-Raid", "antiraid_channel_id", "🚨"),
    ("Logs de Voz", "call_log_channel_id", "🔊"),
    ("Logs da Equipe", "staff_log_channel_id", "👮"),
    ("Logs de Tickets", "ticket_log_channel_id", "🎫"),
]


def format_uptime(start_time: datetime) -> str:
    total_seconds = max(0, int((datetime.now(timezone.utc) - start_time).total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _fmt_id(value: object, prefix: str) -> str:
    parsed = _parse_id(value)
    return f"<{prefix}{parsed}>" if parsed else "`Não definido`"


def _fmt_toggle(enabled: bool) -> str:
    return "🟢 Ativado" if enabled else "🔴 Desativado"


def _invalidate_protection_cache(bot: commands.Bot, guild_id: int) -> None:
    cog = bot.get_cog("BotProtection")
    if cog is not None and hasattr(cog, "invalidate_guild_cache"):
        cog.invalidate_guild_cache(guild_id)


def build_home_embed(bot: commands.Bot, guild: discord.Guild, start_time: datetime) -> discord.Embed:
    latency_ms = round(bot.latency * 1000)
    total_users = sum(g.member_count or 0 for g in bot.guilds)

    embed = discord.Embed(
        title=f"🛠️ Sistema Central de Controle | {guild.name}",
        description=(
            "Painel seguro de operações de administração. "
            "Use as ferramentas abaixo para monitorar métricas e gerenciar configurações globais."
        ),
        color=discord.Color.blurple(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(
        name="📌 Status do Sistema",
        value="🟢 Todos os sistemas operacionais estão funcionando normalmente.",
        inline=False,
    )
    embed.add_field(
        name="📊 Desempenho",
        value=f"⚡ **Latência:** `{latency_ms}ms`\n⏱️ **Tempo de Atividade:** `{format_uptime(start_time)}`",
        inline=False,
    )
    embed.add_field(
        name="🌐 Alcance",
        value=f"🖥️ **Servidores:** `{len(bot.guilds)}`\n👥 **Usuários:** `{total_users}`",
        inline=False,
    )
    embed.set_footer(
        text="Acesso Restrito • Consola do Administrador",
        icon_url=guild.icon.url if guild.icon else (bot.user.display_avatar.url if bot.user else None),
    )
    return embed


async def build_category_embed(guild: discord.Guild, category: str) -> discord.Embed:
    config = await get_guild_config(guild.id)

    if category == "channels":
        embed = discord.Embed(
            title=f"📺 Canais e Logs | {guild.name}",
            description="Selecione abaixo qual tipo de canal e qual canal de destino deseja configurar.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Canais Atuais",
            value="\n".join(
                f"{emoji} **{label}:** {_fmt_id(getattr(config, attr, None), '#')}"
                for label, attr, emoji in CHANNEL_ITEMS
            ),
            inline=False,
        )
    elif category == "security":
        raid_status = _fmt_toggle(bool(getattr(config, "raid_protection_enabled", False)))
        spam_status = _fmt_toggle(bool(getattr(config, "anti_spam_enabled", True)))
        embed = discord.Embed(
            title=f"🛡️ Segurança e Cargos | {guild.name}",
            description="Gerencie o Anti-Raid, o Anti-Spam, o canal de alertas de bot e o Cargo Master do servidor.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Configurações Atuais",
            value=(
                f"**Anti-Raid:** {raid_status}\n"
                f"**Anti-Spam:** {spam_status}\n"
                f"**Canal Anti-Raid:** {_fmt_id(getattr(config, 'antiraid_channel_id', None), '#')}\n"
                f"**Cargo Master:** {_fmt_id(getattr(config, 'master_role_id', None), '@&')}"
            ),
            inline=False,
        )
    else:
        runtime = get_runtime_settings(guild.id)
        cats = runtime.get("ticket_categories", {})
        cat_lines = [f"{opt.emoji} **{opt.label}:** {_fmt_id(cats.get(opt.value), '#')}" for opt in TICKET_TYPES]
        embed = discord.Embed(
            title=f"🎫 Sistema de Tickets | {guild.name}",
            description="Escolha cada tipo de ticket e sua respectiva categoria, edite o cargo de suporte ou publique o painel.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Categorias por Tipo de Ticket", value="\n".join(cat_lines), inline=False)
        embed.add_field(
            name="Cargo de Suporte",
            value=f"🎧 {_fmt_id(getattr(config, 'ticket_support_role_id', None), '@&')}",
            inline=False,
        )

    embed.set_footer(text="Acesso Restrito • Consola do Administrador")
    return embed


class ManagementPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, start_time: datetime) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.start_time = start_time
        self.selected_channel_key: str | None = None
        self.selected_ticket_type: str | None = None
        self.set_home_view()

    def _add_footer_buttons(self, row: int) -> None:
        back_btn = discord.ui.Button(label="Menu Inicial", style=discord.ButtonStyle.secondary, emoji="🏠", row=row)
        back_btn.callback = self.go_home
        close_btn = discord.ui.Button(label="Fechar Console", style=discord.ButtonStyle.secondary, emoji="✖️", row=row)
        close_btn.callback = self.close_console
        self.add_item(back_btn)
        self.add_item(close_btn)

    def _add_button(
        self,
        label: str,
        callback,
        *,
        row: int,
        emoji: str,
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
    ) -> None:
        btn = discord.ui.Button(label=label, style=style, emoji=emoji, row=row)
        btn.callback = callback
        self.add_item(btn)

    def set_home_view(self) -> None:
        self.clear_items()
        cat_select = discord.ui.Select(
            placeholder="Selecione uma categoria administrativa...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Canais e Logs",
                    value="channels",
                    description="Configurar canais de boas-vindas, saídas e logs",
                    emoji="📺",
                ),
                discord.SelectOption(
                    label="Segurança e Cargos",
                    value="security",
                    description="Gerenciar Anti-Raid, Anti-Spam, canal de alerta e cargo Master",
                    emoji="🛡️",
                ),
                discord.SelectOption(
                    label="Sistema de Tickets",
                    value="tickets",
                    description="Configurar categorias por tipo, cargo de suporte e painel",
                    emoji="🎫",
                ),
            ],
            row=0,
        )
        cat_select.callback = self.on_category_select
        self.add_item(cat_select)
        self._add_footer_buttons(row=1)

    def set_category_view(self, category: str) -> None:
        self.clear_items()
        if category == "channels":
            ch_type = discord.ui.Select(
                placeholder="Escolha qual canal deseja configurar...",
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(label=label, value=attr, emoji=emoji) for label, attr, emoji in CHANNEL_ITEMS],
                row=0,
            )
            ch_target = discord.ui.ChannelSelect(
                placeholder="Selecione o canal de texto...",
                channel_types=[discord.ChannelType.text],
                min_values=1,
                max_values=1,
                row=1,
            )
            ch_type.callback = self.on_channel_type_select
            ch_target.callback = self.on_target_channel_select
            self.add_item(ch_type)
            self.add_item(ch_target)
            self._add_footer_buttons(row=2)
        elif category == "security":
            master_role = discord.ui.RoleSelect(placeholder="Selecione o Cargo Master...", min_values=1, max_values=1, row=0)
            master_role.callback = self.on_master_role_select

            antiraid_channel = discord.ui.ChannelSelect(
                placeholder="Selecione o canal de alertas do Anti-Raid (bots)...",
                channel_types=[discord.ChannelType.text],
                min_values=1,
                max_values=1,
                row=1,
            )
            antiraid_channel.callback = self.on_antiraid_channel_select

            self.add_item(master_role)
            self.add_item(antiraid_channel)
            self._add_button("Alternar Anti-Raid", self.toggle_antiraid, row=2, emoji="🛡️")
            self._add_button("Alternar Anti-Spam", self.toggle_antispam, row=2, emoji="🚫")
            self._add_footer_buttons(row=3)
        elif category == "tickets":
            ticket_type = discord.ui.Select(
                placeholder="1. Escolha o tipo de ticket...",
                min_values=1,
                max_values=1,
                options=TICKET_TYPES,
                row=0,
            )
            ticket_cat = discord.ui.ChannelSelect(
                placeholder="2. Selecione a categoria deste ticket...",
                channel_types=[discord.ChannelType.category],
                min_values=1,
                max_values=1,
                row=1,
            )
            support_role = discord.ui.RoleSelect(
                placeholder="Selecione o Cargo de Suporte...",
                min_values=1,
                max_values=1,
                row=2,
            )
            ticket_type.callback = self.on_ticket_type_select
            ticket_cat.callback = self.on_ticket_category_select
            support_role.callback = self.on_support_role_select
            self.add_item(ticket_type)
            self.add_item(ticket_cat)
            self.add_item(support_role)
            self._add_button(
                "Publicar Painel de Tickets",
                self.open_publish_panel_modal,
                row=3,
                emoji="📨",
                style=discord.ButtonStyle.success,
            )
            self._add_footer_buttons(row=4)

    async def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.guild and await require_master(interaction))

    async def _refresh_category(self, interaction: discord.Interaction, category: str) -> None:
        await interaction.response.edit_message(
            embed=await build_category_embed(interaction.guild, category),  # type: ignore[arg-type]
            view=self,
        )

    async def _save_and_refresh(self, interaction: discord.Interaction, category: str, **fields: object) -> None:
        guild_id = interaction.guild.id  # type: ignore[union-attr]
        await update_guild_config(guild_id, **fields)
        _invalidate_protection_cache(self.bot, guild_id)
        await self._refresh_category(interaction, category)

    async def _toggle_field(
        self,
        interaction: discord.Interaction,
        attr: str,
        *,
        default: bool,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return
        config = await get_guild_config(interaction.guild.id)  # type: ignore[union-attr]
        current = bool(getattr(config, attr, default))
        await self._save_and_refresh(interaction, "security", **{attr: not current})

    async def on_category_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        category = interaction.data["values"][0]  # type: ignore[index]
        self.set_category_view(category)
        await self._refresh_category(interaction, category)

    async def on_channel_type_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        self.selected_channel_key = interaction.data["values"][0]  # type: ignore[index]
        await interaction.response.send_message("Agora escolha o **canal de texto** no menu abaixo.", ephemeral=True)

    async def on_target_channel_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        if not self.selected_channel_key:
            return await interaction.response.send_message(
                "⚠️ Escolha primeiro o **tipo de canal** no menu acima.", ephemeral=True
            )
        channel_id = int(interaction.data["values"][0])  # type: ignore[index]
        await self._save_and_refresh(interaction, "channels", **{self.selected_channel_key: channel_id})

    async def on_master_role_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        role_id = int(interaction.data["values"][0])  # type: ignore[index]
        await self._save_and_refresh(interaction, "security", master_role_id=role_id)

    async def on_antiraid_channel_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        channel_id = int(interaction.data["values"][0])  # type: ignore[index]
        await self._save_and_refresh(interaction, "security", antiraid_channel_id=channel_id)

    async def toggle_antiraid(self, interaction: discord.Interaction) -> None:
        await self._toggle_field(interaction, "raid_protection_enabled", default=False)

    async def toggle_antispam(self, interaction: discord.Interaction) -> None:
        await self._toggle_field(interaction, "anti_spam_enabled", default=True)

    async def on_ticket_type_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        self.selected_ticket_type = interaction.data["values"][0]  # type: ignore[index]
        opt = next((o for o in TICKET_TYPES if o.value == self.selected_ticket_type), None)
        nome = opt.label if opt else self.selected_ticket_type
        await interaction.response.send_message(
            f"Agora escolha a **categoria** onde os tickets de **{nome}** serão criados.", ephemeral=True
        )

    async def on_ticket_category_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        if not self.selected_ticket_type:
            return await interaction.response.send_message(
                "⚠️ Escolha primeiro o **tipo de ticket** no menu acima.", ephemeral=True
            )
        category_id = int(interaction.data["values"][0])  # type: ignore[index]
        set_ticket_type_category(interaction.guild.id, self.selected_ticket_type, category_id)  # type: ignore[union-attr]
        await self._refresh_category(interaction, "tickets")

    async def on_support_role_select(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        role_id = int(interaction.data["values"][0])  # type: ignore[index]
        await update_guild_config(interaction.guild.id, ticket_support_role_id=role_id)  # type: ignore[union-attr]
        await self._refresh_category(interaction, "tickets")

    async def open_publish_panel_modal(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        tickets_cog = self.bot.get_cog("Tickets")
        if tickets_cog is None or not hasattr(tickets_cog, "build_panel_embed"):
            return await interaction.response.send_message(
                "O módulo de tickets não está carregado no momento.", ephemeral=True
            )
        await interaction.response.send_modal(PublishPanelModal(tickets_cog, interaction.guild.id))  # type: ignore[union-attr]

    async def go_home(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        self.selected_channel_key = None
        self.selected_ticket_type = None
        self.set_home_view()
        await interaction.response.edit_message(
            embed=build_home_embed(self.bot, interaction.guild, self.start_time),  # type: ignore[arg-type]
            view=self,
        )

    async def close_console(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return
        await interaction.response.edit_message(content="Console encerrado.", embed=None, view=None)
        self.stop()


class Management(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.start_time = datetime.now(timezone.utc)

    @app_commands.command(name="gerenciamento", description="Mostra o painel administrativo e métricas do bot.")
    async def gerenciamento(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return

        embed = build_home_embed(self.bot, interaction.guild, self.start_time)
        view = ManagementPanelView(self.bot, interaction.guild, self.start_time)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Management(bot))