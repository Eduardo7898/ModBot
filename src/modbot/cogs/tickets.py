import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import get_guild_config

FEEDBACK_COLOR = 0xF1C40F
PANEL_COLOR = 0xF1C40F
RANKING_COLOR = 16766208
BRASILIA_TZ = timezone(timedelta(hours=-3))
STATS_FILE = Path("data/ticket_staff_stats.json")
RUNTIME_CONFIG_FILE = Path("data/ticket_panel_runtime.json")

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
_CLOSING_CHANNELS: set[int] = set()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_id(raw: object) -> int | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d]", "", str(raw).strip())
    return int(cleaned) if cleaned else None


def _parse_url(raw: str | None) -> str | None:
    if not raw:
        return None
    url = raw.strip()
    return url if url.startswith(("https://", "http://")) else None


def _stats_bucket(data: dict, guild_id: int) -> dict:
    return data.setdefault(str(guild_id), {"staff": {}, "ranking_message_id": None})


def _staff_entry(data: dict, guild_id: int, staff_id: int) -> dict:
    staff = _stats_bucket(data, guild_id).setdefault("staff", {})
    return staff.setdefault(str(staff_id), {"atendimentos": 0, "ratings": []})


def get_runtime_settings(guild_id: int) -> dict:
    raw = _load_json(RUNTIME_CONFIG_FILE).get(str(guild_id), {})
    bucket = dict(raw) if isinstance(raw, dict) else {}
    cats = bucket.get("ticket_categories")
    bucket["ticket_categories"] = dict(cats) if isinstance(cats, dict) else {}
    return bucket


def save_runtime_settings(guild_id: int, **updates: object) -> dict:
    data = _load_json(RUNTIME_CONFIG_FILE)
    current = get_runtime_settings(guild_id)
    for k, v in updates.items():
        if k == "ticket_categories" and isinstance(v, dict):
            merged = dict(current.get("ticket_categories", {}))
            merged.update(v)
            current["ticket_categories"] = merged
        else:
            current[k] = v
    data[str(guild_id)] = current
    _save_json(RUNTIME_CONFIG_FILE, data)
    return current


def set_ticket_type_category(guild_id: int, ticket_type: str, category_id: int | None) -> None:
    current = get_runtime_settings(guild_id)
    cats = dict(current.get("ticket_categories", {}))
    if category_id:
        cats[ticket_type] = category_id
    else:
        cats.pop(ticket_type, None)
    save_runtime_settings(guild_id, ticket_categories=cats)


def record_ticket_claim(guild_id: int, staff_id: int) -> None:
    data = _load_json(STATS_FILE)
    entry = _staff_entry(data, guild_id, staff_id)
    entry["atendimentos"] = int(entry.get("atendimentos", 0)) + 1
    _save_json(STATS_FILE, data)


def record_ticket_rating(guild_id: int, staff_id: int | None, rating: int) -> None:
    if not staff_id:
        return
    data = _load_json(STATS_FILE)
    entry = _staff_entry(data, guild_id, staff_id)
    ratings = list(entry.get("ratings", []))
    ratings.append(max(1, min(5, int(rating))))
    entry["ratings"] = ratings
    _save_json(STATS_FILE, data)


def build_ranking_embed(guild_id: int) -> discord.Embed:
    staff_map = _stats_bucket(_load_json(STATS_FILE), guild_id).get("staff", {})
    rows = []
    for staff_id, info in staff_map.items():
        if not isinstance(info, dict):
            continue
        atend = int(info.get("atendimentos", 0))
        ratings = [float(r) for r in info.get("ratings", []) if isinstance(r, (int, float, str))]
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
            lines.append(f"\n{header} <@{staff_id}>\n└ 🎫 Atend: `{atend}` | ⭐ Média: `{avg:.1f}` ({count} av.)")
        desc = "".join(lines)

    now = datetime.now(BRASILIA_TZ).strftime("%H:%M")
    embed = discord.Embed(title="🏆 RANKING DA STAFF", description=desc, color=RANKING_COLOR)
    embed.set_footer(text=f"Última Atualização • {now}")
    return embed


async def _get_text_channel(bot: commands.Bot, channel_id: int | None) -> discord.TextChannel | None:
    if not channel_id:
        return None
    ch = bot.get_channel(channel_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    return ch if isinstance(ch, discord.TextChannel) else None


async def sync_ranking_channel(bot: commands.Bot, guild_id: int, force_new: bool = False) -> discord.Message | None:
    runtime = get_runtime_settings(guild_id)
    ch = await _get_text_channel(bot, _parse_id(runtime.get("ranking_channel_id")))
    if not ch:
        return None

    embed = build_ranking_embed(guild_id)
    data = _load_json(STATS_FILE)
    bucket = _stats_bucket(data, guild_id)
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
        _save_json(STATS_FILE, data)
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


def _next_ticket_number(category: discord.CategoryChannel) -> int:
    nums = [int(m.group(1)) for ch in category.text_channels if (m := re.match(r"^ticket-(\d+)", ch.name))]
    return (max(nums) + 1) if nums else 1


def _parse_topic(topic: str | None) -> tuple[int | None, int | None]:
    if not topic:
        return None, None
    opener = re.search(r"\((\d{17,20})\)", topic)
    staff = re.search(r"staff:(\d{17,20})", topic)
    return (int(opener.group(1)) if opener else None, int(staff.group(1)) if staff else None)


async def _set_claimed_staff(channel: discord.TextChannel, staff: discord.Member) -> None:
    base = re.sub(r"\s*\|\s*staff:\d{17,20}", "", channel.topic or "").strip(" |")
    new_topic = f"{base} | staff:{staff.id}" if base else f"staff:{staff.id}"
    try:
        await channel.edit(topic=new_topic[:1024])
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


def _ticket_overwrites(
    guild: discord.Guild, opener: discord.Member, support_role: discord.Role | None
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
        ),
    }
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )
    return overwrites


class TicketRatingView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, staff_id: int | None, staff_label: str):
        super().__init__(timeout=86400)
        self.bot = bot
        self.guild_id = guild_id
        self.staff_id = staff_id
        self.staff_label = staff_label
        self.rated = False
        for n in range(1, 6):
            btn = discord.ui.Button(label=str(n), emoji="⭐", style=discord.ButtonStyle.secondary)
            btn.callback = self._make_rating_callback(n)
            self.add_item(btn)

    def _make_rating_callback(self, stars: int):
        async def callback(interaction: discord.Interaction):
            if self.rated:
                return await interaction.response.send_message("Você já enviou sua avaliação.", ephemeral=True)

            self.rated = True
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            record_ticket_rating(self.guild_id, self.staff_id, stars)
            word = "estrela" if stars == 1 else "estrelas"
            await interaction.response.edit_message(
                content=f"Muito obrigado! Você avaliou o atendimento com **{stars}** {word}.",
                embed=None,
                view=self,
            )
            await self.send_log(stars, interaction.user)
            if isinstance(self.bot, commands.Bot):
                await sync_ranking_channel(self.bot, self.guild_id)

        return callback

    async def send_log(self, rating: int, user: discord.User | discord.Member):
        runtime = get_runtime_settings(self.guild_id)
        ch = await _get_text_channel(self.bot, _parse_id(runtime.get("feedback_channel_id")))
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


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        select = discord.ui.Select(
            placeholder="Selecione uma opção",
            min_values=1,
            max_values=1,
            options=TICKET_TYPES,
            custom_id="tickets:categoria",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def _reset(self, interaction: discord.Interaction):
        if interaction.message:
            try:
                await interaction.message.edit(view=TicketPanel())
            except discord.HTTPException:
                pass

    async def on_select(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)

        val = interaction.data["values"][0]  # type: ignore[index]
        opt = next((o for o in TICKET_TYPES if o.value == val), None)
        cat_label = opt.label if opt else val.title()
        cat_emoji = str(opt.emoji) if opt and opt.emoji else "🎫"

        runtime = get_runtime_settings(guild.id)
        cat_id = _parse_id(runtime.get("ticket_categories", {}).get(val))
        category = guild.get_channel(cat_id) if cat_id else None
        if not isinstance(category, discord.CategoryChannel):
            await self._reset(interaction)
            return await interaction.response.send_message(
                f"A categoria do ticket **{cat_label}** ainda não foi configurada em `/gerenciamento`.",
                ephemeral=True,
            )

        config = await get_guild_config(guild.id)
        support_role = guild.get_role(config.ticket_support_role_id) if config.ticket_support_role_id else None
        num = _next_ticket_number(category)

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{num}",
                category=category,
                overwrites=_ticket_overwrites(guild, interaction.user, support_role),
                topic=f"Ticket #{num} de {interaction.user} ({interaction.user.id}) | categoria: {val}",
                reason=f"Ticket #{num} aberto por {interaction.user} ({interaction.user.id})",
            )
            embed = _build_ticket_open_embed(interaction.user, num, cat_label, cat_emoji, channel.created_at)
            mention = f"{support_role.mention} {interaction.user.mention}" if support_role else interaction.user.mention
            controls = TicketControls(
                bot=interaction.client, opener_id=interaction.user.id, support_role_id=config.ticket_support_role_id
            )
            await channel.send(
                content=mention,
                embed=embed,
                view=controls,
                allowed_mentions=discord.AllowedMentions(users=True, roles=bool(support_role), everyone=False),
            )
            await self._reset(interaction)
            await interaction.response.send_message(f"Ticket **#{num}** criado: {channel.mention}", ephemeral=True)
        except discord.Forbidden:
            await self._reset(interaction)
            await interaction.response.send_message(
                "Não tenho permissão para criar canais. Verifique Manage Channels.", ephemeral=True
            )


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

        allowed = (opener_id is not None and interaction.user.id == opener_id) or _is_staff(
            interaction.user, support_role_id
        )
        return allowed, opener_id, support_role_id

    @discord.ui.button(label="Fechar ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed, opener_id, support_role_id = await self._context(interaction)
        if not allowed or not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Somente quem abriu ou a equipe de suporte pode fechar.", ephemeral=True
            )

        channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        if channel and channel.id in _CLOSING_CHANNELS:
            return await interaction.response.send_message("Este ticket já está sendo fechado.", ephemeral=True)

        if channel:
            _CLOSING_CHANNELS.add(channel.id)

        try:
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
                    description=(
                        f"Seu ticket em **{interaction.guild.name}** foi encerrado.\n"
                        "Selecione uma nota de **1 a 5** estrelas para avaliar o atendimento:"
                    ),
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
        finally:
            if channel:
                _CLOSING_CHANNELS.discard(channel.id)

    @discord.ui.button(label="Adicionar membro", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="ticket:add_member")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed, _, _ = await self._context(interaction)
        if not allowed:
            return await interaction.response.send_message(
                "Somente quem abriu ou a equipe de suporte pode adicionar membros.", ephemeral=True
            )
        await interaction.response.send_message("Função de adicionar membro indisponível no momento.", ephemeral=True)


class PublishPanelModal(discord.ui.Modal, title="Configurar e Publicar Painel"):
    feedback_channel_input = discord.ui.TextInput(
        label="ID do canal de feedback",
        placeholder="Ex: 1562820906949148765 (opcional)",
        required=False,
        max_length=30,
    )
    ranking_channel_input = discord.ui.TextInput(
        label="ID do canal de ranking",
        placeholder="Ex: 1572970836145471608 (opcional)",
        required=False,
        max_length=30,
    )
    image_url_input = discord.ui.TextInput(
        label="URL da imagem do painel",
        placeholder="https://... (opcional)",
        required=False,
        max_length=500,
    )

    def __init__(self, cog: "Tickets", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        current = get_runtime_settings(guild_id)
        if current.get("feedback_channel_id"):
            self.feedback_channel_input.default = str(current["feedback_channel_id"])
        if current.get("ranking_channel_id"):
            self.ranking_channel_input.default = str(current["ranking_channel_id"])
        if current.get("image_url"):
            self.image_url_input.default = str(current["image_url"])

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)

        feedback_id = _parse_id(self.feedback_channel_input.value)
        ranking_id = _parse_id(self.ranking_channel_input.value)
        image_url = _parse_url(self.image_url_input.value)

        if self.image_url_input.value.strip() and not image_url:
            return await interaction.response.send_message(
                "A URL da imagem precisa começar com `https://` ou `http://`.", ephemeral=True
            )

        save_runtime_settings(
            self.guild_id,
            feedback_channel_id=feedback_id,
            ranking_channel_id=ranking_id,
            image_url=image_url,
        )
        embed = await self.cog.build_panel_embed(self.guild_id, image_url=image_url)
        await interaction.response.send_message(embed=embed, view=TicketPanel())

        if ranking_id and isinstance(interaction.client, commands.Bot):
            await sync_ranking_channel(interaction.client, self.guild_id, force_new=True)


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

    async def build_panel_embed(self, guild_id: int, image_url: str | None = None) -> discord.Embed:
        config = await get_guild_config(guild_id)
        runtime = get_runtime_settings(guild_id)
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
        if img := (image_url or runtime.get("image_url") or getattr(config, "ticket_panel_image", None)):
            embed.set_image(url=img)
        if thumb := getattr(config, "ticket_panel_thumbnail", None):
            embed.set_thumbnail(url=thumb)
        return embed

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