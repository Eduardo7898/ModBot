import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import get_guild_config
from modbot.utils.permissions import require_master

FEEDBACK_CHANNEL_ID = 1562820906949148765
RANKING_CHANNEL_ID = 1572970836145471608
FEEDBACK_COLOR = 0xF1C40F
PANEL_COLOR = 0xF1C40F
RANKING_COLOR = 16766208
BRASILIA_TZ = timezone(timedelta(hours=-3))
STATS_FILE = Path("data/ticket_staff_stats.json")

BANNER_URL = (
    "https://cdn.discordapp.com/attachments/1565372877963010168/1571965002284273904/"
    "rn_image_picker_lib_temp_f7a48201-d2a1-4a24-a051-2dd3c302c797.jpg"
    "?ex=6aff48fe&is=6afdf77e&hm=8d7cdf648f13dded74f146a34141b8cd99c7c3ea177a50c415a141b6d5c72c04&"
)

PANEL_TITLE = "「 BDV 」• Central de Atendimento"
PANEL_DESC = (
    "Bem-vindo à **Central de Suporte da BDV!**\n"
    "Selecione a categoria abaixo para abrir um ticket.\n\n"
    "❓ **Dúvidas** — Esclarecimentos e orientações\n"
    "🤝 **Parcerias** — Propostas de colaboração\n"
    "📢 **Denúncias** — Reporte de players ou violações\n"
    "💰 **Financeiro** — Compra de mods/EQUIP BDV/VIP\n\n"
    "⚠️ Use os tickets com responsabilidade.\n"
    "Abusos poderão resultar em punições.\n\n"
    "「 BDV 」• Selecione uma categoria abaixo"
)
PANEL_FOOTER = "BAILE DA VILA • © Todos os direitos reservados."

TICKET_TYPES = [
    discord.SelectOption(label="Financeiro", value="financeiro", emoji="💠", description="Compras de mods/EQUIP BDV/VIP"),
    discord.SelectOption(label="Parcerias", value="parcerias", emoji="🤝", description="Proposta de parceria."),
    discord.SelectOption(label="Dúvidas", value="duvidas", emoji="❓", description="Esclarecimento e orientação"),
    discord.SelectOption(label="Denuncia", value="denuncia", emoji="🆘", description="Repórter de players ou violações STAFF"),
]

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _load_stats() -> dict:
    if not STATS_FILE.exists():
        return {}
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_stats(data: dict) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_guild_bucket(data: dict, guild_id: int) -> dict:
    return data.setdefault(str(guild_id), {"staff": {}, "ranking_message_id": None})


def _get_staff_entry(data: dict, guild_id: int, staff_id: int) -> dict:
    bucket = _get_guild_bucket(data, guild_id)
    staff_map = bucket.setdefault("staff", {})
    return staff_map.setdefault(str(staff_id), {"atendimentos": 0, "ratings": []})


def record_ticket_claim(guild_id: int, staff_id: int) -> None:
    data = _load_stats()
    entry = _get_staff_entry(data, guild_id, staff_id)
    entry["atendimentos"] = int(entry.get("atendimentos", 0)) + 1
    _save_stats(data)


def record_ticket_rating(guild_id: int, staff_id: int | None, rating: int) -> None:
    if not staff_id:
        return
    data = _load_stats()
    entry = _get_staff_entry(data, guild_id, staff_id)
    ratings = list(entry.get("ratings", []))
    ratings.append(int(rating))
    entry["ratings"] = ratings
    _save_stats(data)


def build_ranking_embed(guild_id: int) -> discord.Embed:
    bucket = _get_guild_bucket(_load_stats(), guild_id)
    staff_map = bucket.get("staff", {})
    rows = []
    for staff_id, info in staff_map.items():
        atend = int(info.get("atendimentos", 0))
        ratings = [float(r) for r in info.get("ratings", [])]
        count = len(ratings)
        avg = (sum(ratings) / count) if count else 0.0
        rows.append((atend, avg, count, int(staff_id)))

    rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    top_rows = rows[:15]

    if not top_rows:
        desc = "Membros da equipe que mais se destacaram no suporte.\n\nNenhum atendimento registrado ainda."
    else:
        lines = ["Membros da equipe que mais se destacaram no suporte."]
        for pos, (atend, avg, count, staff_id) in enumerate(top_rows, start=1):
            header = MEDALS.get(pos, f"**{pos}.**")
            lines.append(
                f"\n{header} <@{staff_id}>\n"
                f"└ 🎫 Atend: `{atend}` | ⭐ Média: `{avg:.1f}` ({count} av.)"
            )
        desc = "".join(lines)

    now = datetime.now(BRASILIA_TZ).strftime("%H:%M")
    embed = discord.Embed(title="🏆 RANKING DA STAFF", description=desc, color=RANKING_COLOR)
    embed.set_footer(text=f"Última Atualização • {now}")
    return embed


async def _get_text_channel(bot: commands.Bot, channel_id: int) -> discord.TextChannel | None:
    ch = bot.get_channel(channel_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    return ch if isinstance(ch, discord.TextChannel) else None


async def sync_ranking_channel(bot: commands.Bot, guild_id: int, force_new: bool = False) -> discord.Message | None:
    ch = await _get_text_channel(bot, RANKING_CHANNEL_ID)
    if not ch:
        return None

    embed = build_ranking_embed(guild_id)
    data = _load_stats()
    bucket = _get_guild_bucket(data, guild_id)
    msg_id = bucket.get("ranking_message_id")

    if msg_id and not force_new:
        try:
            msg = await ch.fetch_message(int(msg_id))
            await msg.edit(embed=embed)
            return msg
        except discord.HTTPException:
            pass

    try:
        msg = await ch.send(embed=embed)
        bucket["ranking_message_id"] = msg.id
        _save_stats(data)
        return msg
    except discord.HTTPException:
        return None


def _has_support_role(member: discord.Member, role_id: int | None) -> bool:
    return bool(role_id and any(r.id == role_id for r in member.roles))


def _is_staff(member: discord.Member, role_id: int | None, opener_id: int | None = None) -> bool:
    if member.bot or (opener_id is not None and member.id == opener_id):
        return False
    return bool(
        member.guild_permissions.manage_channels
        or member.guild_permissions.administrator
        or _has_support_role(member, role_id)
    )


def _next_ticket_number(guild: discord.Guild, category: discord.CategoryChannel | None) -> int:
    channels = category.text_channels if category else guild.text_channels
    nums = [int(m.group(1)) for ch in channels if (m := re.match(r"^ticket-(\d+)", ch.name))]
    return (max(nums) + 1) if nums else 1


def _parse_topic(topic: str | None) -> tuple[int | None, int | None]:
    if not topic:
        return None, None
    opener = re.search(r"\((\d{17,20})\)", topic)
    staff = re.search(r"staff:(\d{17,20})", topic)
    return (int(opener.group(1)) if opener else None, int(staff.group(1)) if staff else None)


async def _set_claimed_staff(channel: discord.TextChannel, staff: discord.Member) -> None:
    base = re.sub(r"\s*\|\s*staff:\d{17,20}", "", channel.topic or "")
    try:
        await channel.edit(topic=f"{base} | staff:{staff.id}".strip(" |")[:1024])
    except discord.HTTPException:
        pass


async def _find_staff(
    channel: discord.TextChannel, role_id: int | None, opener_id: int | None, closer: discord.Member
) -> discord.Member | None:
    _, claimed_id = _parse_topic(channel.topic)
    if claimed_id and (claimed := channel.guild.get_member(claimed_id)) and not claimed.bot:
        return claimed
    try:
        async for msg in channel.history(limit=100):
            if isinstance(msg.author, discord.Member) and _is_staff(msg.author, role_id, opener_id):
                return msg.author
    except discord.HTTPException:
        pass
    return closer if _is_staff(closer, role_id, opener_id) else None


async def _resolve_user(client: discord.Client, guild: discord.Guild, user_id: int) -> discord.User | discord.Member | None:
    if member := guild.get_member(user_id):
        return member
    try:
        return await client.fetch_user(user_id)
    except discord.HTTPException:
        return None


def _build_ticket_open_embed(
    user: discord.Member, num: int, cat_label: str, cat_emoji: str, created_at: datetime
) -> discord.Embed:
    ts = int(created_at.timestamp())
    embed = discord.Embed(
        title=f"「 {cat_emoji} {cat_label} 」• Ticket #{num}",
        description=(
            f"👤 **Usuário:** {user.mention}\n"
            f"🆔 **ID:**\n```\n{user.id}\n```\n"
            f"📂 **Categoria:** {cat_emoji}\n{cat_label}\n"
            f"🕒 **Aberto em:**\n<t:{ts}:F> (<t:{ts}:R>)\n\n"
            f"Por favor, descreva seu problema detalhadamente.\n"
            f"Um membro da **Staff** irá atendê-lo em breve.\n\n"
            f"⏳ Aguarde com paciência — estamos aqui"
        ),
        color=PANEL_COLOR,
    )
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    return embed


class RatingButton(discord.ui.Button):
    def __init__(self, stars: int):
        super().__init__(label=str(stars), emoji="⭐", style=discord.ButtonStyle.secondary)
        self.stars = stars

    async def callback(self, interaction: discord.Interaction):
        view: TicketRatingView = self.view  # type: ignore[assignment]
        if view.rated:
            return await interaction.response.send_message("Você já enviou sua avaliação.", ephemeral=True)

        view.rated = True
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        record_ticket_rating(view.guild_id, view.staff_id, self.stars)
        word = "estrela" if self.stars == 1 else "estrelas"
        await interaction.response.edit_message(
            content=f"Muito obrigado! Você avaliou o atendimento com **{self.stars}** {word}.",
            embed=None,
            view=view,
        )
        await view.send_log(self.stars, interaction.user)
        if isinstance(view.bot, commands.Bot):
            await sync_ranking_channel(view.bot, view.guild_id)


class TicketRatingView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, staff_id: int | None, staff_label: str):
        super().__init__(timeout=86400)
        self.bot = bot
        self.guild_id = guild_id
        self.staff_id = staff_id
        self.staff_label = staff_label
        self.rated = False
        for n in range(1, 6):
            self.add_item(RatingButton(n))

    async def send_log(self, rating: int, user: discord.User | discord.Member):
        ch = await _get_text_channel(self.bot, FEEDBACK_CHANNEL_ID)
        if not ch:
            return
        now = datetime.now(BRASILIA_TZ).strftime("%d/%m/%Y %H:%M")
        embed = discord.Embed(
            title="🔆 Novo Feedback de Atendimento",
            description=(
                f"Um usuário acabou de avaliar o atendimento do staff {self.staff_label}.\n\n"
                f"👮‍♂️ **Staff Avaliado:**\n{self.staff_label}\n\n"
                f"⭐ **Nota:**\n{'⭐' * rating}{'☆' * (5 - rating)} ({rating}/5)\n\n"
                f"👤 **Avaliado por:**\n{user.mention}"
            ),
            color=FEEDBACK_COLOR,
        )
        embed.set_footer(text=f"ID do Staff: {self.staff_id or 'N/A'} | ID do Usuário: {user.id} | {now}")
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Selecione uma opção",
            min_values=1,
            max_values=1,
            options=TICKET_TYPES,
            custom_id="tickets:categoria",
        )

    async def _reset(self, interaction: discord.Interaction):
        if interaction.message:
            try:
                await interaction.message.edit(view=TicketPanel())
            except discord.HTTPException:
                pass

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)

        config = await get_guild_config(guild.id)
        category = guild.get_channel(config.ticket_category_id) if config.ticket_category_id else None
        if not isinstance(category, discord.CategoryChannel):
            await self._reset(interaction)
            return await interaction.response.send_message("A categoria de tickets ainda não foi configurada.", ephemeral=True)

        support_role = guild.get_role(config.ticket_support_role_id) if config.ticket_support_role_id else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        val = self.values[0]
        opt = next((o for o in TICKET_TYPES if o.value == val), None)
        cat_label = opt.label if opt else val.title()
        cat_emoji = str(opt.emoji) if opt and opt.emoji else "🎫"
        num = _next_ticket_number(guild, category)

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{num}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{num} de {interaction.user} ({interaction.user.id}) | categoria: {val}",
                reason=f"Ticket #{num} aberto por {interaction.user} ({interaction.user.id})",
            )
            embed = _build_ticket_open_embed(interaction.user, num, cat_label, cat_emoji, channel.created_at)
            mention = f"{support_role.mention} {interaction.user.mention}" if support_role else interaction.user.mention
            controls = TicketControls(bot=interaction.client, opener_id=interaction.user.id, support_role_id=config.ticket_support_role_id)
            await channel.send(content=mention, embed=embed, view=controls, allowed_mentions=discord.AllowedMentions(users=True, roles=bool(support_role), everyone=False))
            await self._reset(interaction)
            await interaction.response.send_message(f"Ticket **#{num}** criado: {channel.mention}", ephemeral=True)
        except discord.Forbidden:
            await self._reset(interaction)
            await interaction.response.send_message("Não tenho permissão para criar canais. Verifique Manage Channels.", ephemeral=True)


class TicketControls(discord.ui.View):
    def __init__(self, bot: commands.Bot | None = None, opener_id: int | None = None, support_role_id: int | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.opener_id = opener_id
        self.support_role_id = support_role_id

    async def _context(self, interaction: discord.Interaction) -> tuple[bool, int | None, int | None]:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False, None, None

        topic = interaction.channel.topic if isinstance(interaction.channel, discord.TextChannel) else None
        opener_id, _ = _parse_topic(topic)
        if opener_id is None:
            opener_id = self.opener_id

        support_role_id = self.support_role_id
        if support_role_id is None:
            config = await get_guild_config(interaction.guild.id)
            support_role_id = config.ticket_support_role_id

        allowed = (opener_id is not None and interaction.user.id == opener_id) or _is_staff(interaction.user, support_role_id)
        return allowed, opener_id, support_role_id

    @discord.ui.button(label="Fechar ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed, opener_id, support_role_id = await self._context(interaction)
        if not allowed or not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Somente quem abriu ou a equipe de suporte pode fechar.", ephemeral=True)

        channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        staff = await _find_staff(channel, support_role_id, opener_id, interaction.user) if channel else None
        await interaction.response.send_message("O ticket será fechado em 5 segundos.", ephemeral=True)

        if opener_id is not None and (opener := await _resolve_user(interaction.client, interaction.guild, opener_id)):
            view = TicketRatingView(
                bot=interaction.client,
                guild_id=interaction.guild.id,
                staff_id=staff.id if staff else None,
                staff_label=staff.mention if staff else "Staff não identificado",
            )
            dm_embed = discord.Embed(
                title="⭐ Avaliação de Atendimento",
                description=f"Seu ticket em **{interaction.guild.name}** foi encerrado.\nSelecione uma nota de **1 a 5** estrelas para avaliar o atendimento:",
                color=FEEDBACK_COLOR,
            )
            try:
                await opener.send(embed=dm_embed, view=view)
            except discord.HTTPException:
                pass

        await asyncio.sleep(5)
        if channel:
            try:
                await channel.delete(reason=f"Ticket fechado por {interaction.user} ({interaction.user.id})")
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Adicionar membro", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="ticket:add_member")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed, _, _ = await self._context(interaction)
        if not allowed:
            return await interaction.response.send_message("Somente quem abriu ou a equipe de suporte pode adicionar membros.", ephemeral=True)
        await interaction.response.send_message("Função de adicionar membro indisponível no momento.", ephemeral=True)


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketPanel())
        self.bot.add_view(TicketControls(bot=bot))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.channel, discord.TextChannel):
            return
        if not isinstance(message.author, discord.Member):
            return
        opener_id, claimed_staff_id = _parse_topic(message.channel.topic)
        if opener_id is None or claimed_staff_id is not None or message.author.id == opener_id:
            return

        config = await get_guild_config(message.guild.id)
        if _has_support_role(message.author, config.ticket_support_role_id):
            await _set_claimed_staff(message.channel, message.author)
            record_ticket_claim(message.guild.id, message.author.id)
            embed = discord.Embed(
                description=f"👮‍♂️ Ticket assumido automaticamente por {message.author.mention}.",
                color=PANEL_COLOR,
            )
            await message.channel.send(embed=embed)
            await sync_ranking_channel(self.bot, message.guild.id)

    async def build_panel_embed(self, guild_id: int) -> discord.Embed:
        config = await get_guild_config(guild_id)
        color = getattr(config, "ticket_panel_color", None)
        embed = discord.Embed(
            title=getattr(config, "ticket_panel_title", None) or PANEL_TITLE,
            description=getattr(config, "ticket_panel_desc", None) or PANEL_DESC,
            color=color if color is not None else PANEL_COLOR,
        )
        footer = getattr(config, "ticket_panel_footer", None)
        if footer is None:
            footer = PANEL_FOOTER
        if footer:
            embed.set_footer(text=footer, icon_url=getattr(config, "ticket_panel_footer_icon", None))
        if img := (getattr(config, "ticket_panel_image", None) or BANNER_URL):
            embed.set_image(url=img)
        if thumb := getattr(config, "ticket_panel_thumbnail", None):
            embed.set_thumbnail(url=thumb)
        return embed

    @app_commands.command(name="ticket_painel", description="Publica o painel customizado para abrir tickets.")
    async def ticket_painel(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return
        await interaction.response.send_message(embed=await self.build_panel_embed(interaction.guild.id), view=TicketPanel())

    @app_commands.command(name="ticket_ranking", description="Envia ou atualiza o ranking da staff no canal configurado.")
    async def ticket_ranking(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        msg = await sync_ranking_channel(self.bot, interaction.guild.id, force_new=True)
        if msg:
            await interaction.response.send_message(f"Ranking atualizado em {msg.channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(embed=build_ranking_embed(interaction.guild.id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tickets(bot))