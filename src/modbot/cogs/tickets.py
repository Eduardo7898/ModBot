import asyncio
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import GuildConfig, StaffTicketStat, Ticket, get_guild_config

FEEDBACK_COLOR = 0xF1C40F
PANEL_COLOR = 0xF1C40F
RANKING_COLOR = 16766208
BRASILIA_TZ = timezone(timedelta(hours=-3))
RUNTIME_CONFIG_FILE = Path("data/ticket_panel_runtime.json")

DEFAULT_PANEL_TITLE = "Central de Atendimento e Suporte"
DEFAULT_PANEL_DESC = (
    "Bem-vindo à nossa **Central de Atendimento!**\n"
    "Selecione uma categoria abaixo para abrir um ticket exclusivo com a nossa equipe.\n\n"
    "❓ **Dúvidas** — Esclarecimentos e orientações\n"
    "🤝 **Parcerias** — Propostas de colaboração\n"
    "📢 **Denúncias** — Reporte de infrações ou violações\n"
    "💰 **Financeiro** — Doações, compras e VIP\n\n"
    "⚠️ Use os tickets com responsabilidade.\n"
    "Abusos poderão resultar em punições."
)
DEFAULT_PANEL_FOOTER = "Sistema de Atendimento • Todos os direitos reservados."

TICKET_TYPES = [
    discord.SelectOption(label="Financeiro", value="financeiro", emoji="💠", description="Assuntos financeiros, VIP ou compras"),
    discord.SelectOption(label="Parcerias", value="parcerias", emoji="🤝", description="Propostas de colaboração e eventos"),
    discord.SelectOption(label="Dúvidas", value="duvidas", emoji="❓", description="Esclarecimento e orientação geral"),
    discord.SelectOption(label="Denúncia", value="denuncia", emoji="🆘", description="Reportar jogadores ou condutas"),
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


async def record_ticket_claim(guild_id: int, staff_id: int) -> None:
    stat, _ = await StaffTicketStat.get_or_create(guild_id=guild_id, staff_id=staff_id)
    stat.atendimentos += 1
    await stat.save(update_fields=["atendimentos"])


async def record_ticket_rating(guild_id: int, staff_id: int | None, rating: int) -> None:
    if not staff_id:
        return
    stat, _ = await StaffTicketStat.get_or_create(guild_id=guild_id, staff_id=staff_id)
    stat.total_ratings += 1
    stat.rating_sum += max(1, min(5, int(rating)))
    await stat.save(update_fields=["total_ratings", "rating_sum"])


async def build_ranking_embed(guild_id: int) -> discord.Embed:
    stats = await StaffTicketStat.filter(guild_id=guild_id).all()
    rows = []
    for stat in stats:
        atend = stat.atendimentos
        count = stat.total_ratings
        avg = (stat.rating_sum / count) if count else 0.0
        rows.append((atend, avg, count, stat.staff_id))

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
    target_channel_id = _parse_id(runtime.get("ranking_channel_id"))
    if not target_channel_id:
        config = await get_guild_config(guild_id)
        target_channel_id = config.ticket_log_channel_id

    ch = await _get_text_channel(bot, target_channel_id)
    if not ch:
        return None

    embed = await build_ranking_embed(guild_id)
    msg_id = runtime.get("ranking_message_id")

    if msg_id and not force_new:
        try:
            msg = await ch.fetch_message(int(msg_id))
            await msg.edit(embed=embed)
            return msg
        except discord.HTTPException:
            pass

    try:
        msg = await ch.send(embed=embed)
        save_runtime_settings(guild_id, ranking_message_id=msg.id)
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
            "Por favor, descreva seu problema detalhadamente.\n"
            "Um membro da **Equipe de Suporte** irá atendê-lo em breve.\n\n"
            "⏳ Aguarde com paciência — estamos aqui para ajudar."
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


class AddMemberModal(discord.ui.Modal, title="Adicionar Membro ao Ticket"):
    member_input = discord.ui.TextInput(
        label="ID ou Menção do Usuário",
        placeholder="Ex: 123456789012345678",
        required=True,
        max_length=40,
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.member_input.value.strip()
        uid = _parse_id(raw)
        if not uid or not interaction.guild:
            return await interaction.response.send_message("❌ ID de usuário inválido.", ephemeral=True)

        target = interaction.guild.get_member(uid)
        if not target:
            try:
                target = await interaction.guild.fetch_member(uid)
            except discord.HTTPException:
                target = None

        if not target:
            return await interaction.response.send_message("❌ Membro não encontrado no servidor.", ephemeral=True)

        try:
            await self.channel.set_permissions(
                target,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                reason=f"Adicionado ao ticket por {interaction.user}",
            )
            await interaction.response.send_message(f"✅ {target.mention} foi adicionado ao ticket com sucesso!")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Sem permissão para alterar permissões deste canal.", ephemeral=True)


class TicketRatingView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, staff_id: int | None, staff_label: str, ticket_number: int | None = None):
        super().__init__(timeout=86400)
        self.bot = bot
        self.guild_id = guild_id
        self.staff_id = staff_id
        self.staff_label = staff_label
        self.ticket_number = ticket_number
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

            await record_ticket_rating(self.guild_id, self.staff_id, stars)

            # Atualiza nota no banco de dados
            if self.ticket_number:
                t = await Ticket.filter(guild_id=self.guild_id, ticket_number=self.ticket_number).first()
                if t:
                    t.rating = stars
                    await t.save(update_fields=["rating"])

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
        target_ch = _parse_id(runtime.get("feedback_channel_id"))
        if not target_ch:
            config = await get_guild_config(self.guild_id)
            target_ch = config.ticket_log_channel_id

        ch = await _get_text_channel(self.bot, target_ch)
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

        config = await get_guild_config(guild.id)
        runtime = get_runtime_settings(guild.id)
        cat_id = _parse_id(runtime.get("ticket_categories", {}).get(val)) or config.ticket_category_id
        category = guild.get_channel(cat_id) if cat_id else None

        if not isinstance(category, discord.CategoryChannel):
            await self._reset(interaction)
            return await interaction.response.send_message(
                f"A categoria do ticket **{cat_label}** ainda não foi configurada em `/gerenciamento`.",
                ephemeral=True,
            )

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

            # Registra o ticket no banco de dados
            await Ticket.create(
                guild_id=guild.id,
                ticket_number=num,
                channel_id=channel.id,
                opener_id=interaction.user.id,
                category=val,
                status="open",
            )

            embed = _build_ticket_open_embed(interaction.user, num, cat_label, cat_emoji, channel.created_at)
            mention = f"{support_role.mention} {interaction.user.mention}" if support_role else interaction.user.mention
            controls = TicketControls(
                bot=interaction.client, opener_id=interaction.user.id, support_role_id=config.ticket_support_role_id, ticket_number=num
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
    def __init__(
        self,
        bot: commands.Bot | None = None,
        opener_id: int | None = None,
        support_role_id: int | None = None,
        ticket_number: int | None = None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.opener_id = opener_id
        self.support_role_id = support_role_id
        self.ticket_number = ticket_number

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
            num_match = re.search(r"\d+", channel.name) if channel else None
            ticket_num = int(num_match.group()) if num_match else (self.ticket_number or 0)

            await interaction.response.send_message("O ticket será arquivado e fechado em 5 segundos...", ephemeral=True)

            # Gera transcript de mensagens
            transcript_lines = [
                f"=== HISTÓRICO DO TICKET #{ticket_num} ({channel.name if channel else 'N/A'}) ===",
                f"Servidor: {interaction.guild.name} ({interaction.guild.id})",
                f"Aberto por ID: {opener_id or 'N/A'}",
                f"Encerrado por: {interaction.user} ({interaction.user.id})",
                f"Atendido por: {staff} ({staff.id})" if staff else "Atendido por: N/A",
                f"Data de encerramento: {discord.utils.utcnow().strftime('%d/%m/%Y %H:%M:%S UTC')}",
                "=" * 60,
                "",
            ]

            if channel:
                try:
                    async for msg in channel.history(limit=300, oldest_first=True):
                        ts = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
                        author = f"{msg.author} ({msg.author.id})"
                        content = msg.clean_content or "[Sem conteúdo de texto]"
                        if msg.attachments:
                            content += " | Anexos: " + ", ".join(a.url for a in msg.attachments)
                        transcript_lines.append(f"[{ts}] {author}: {content}")
                except Exception:
                    transcript_lines.append("[Aviso: histórico parcialmente coletado]")

            transcript_bytes = "\n".join(transcript_lines).encode("utf-8")

            # Atualiza status no banco de dados
            if channel:
                ticket_rec = await Ticket.filter(channel_id=channel.id).first()
                if not ticket_rec and opener_id:
                    ticket_rec = await Ticket.filter(guild_id=interaction.guild.id, opener_id=opener_id, status="open").order_by("-id").first()
                if ticket_rec:
                    ticket_rec.status = "closed"
                    ticket_rec.closed_at = discord.utils.utcnow()
                    if staff:
                        ticket_rec.staff_id = staff.id
                    await ticket_rec.save()

            # Envia transcript para o canal de logs configurado
            config = await get_guild_config(interaction.guild.id)
            log_cid = config.ticket_log_channel_id
            log_channel = interaction.guild.get_channel(log_cid) if log_cid else None

            if isinstance(log_channel, discord.TextChannel):
                log_embed = discord.Embed(
                    title=f"📁 Ticket #{ticket_num} Encerrado",
                    description=(
                        f"• **Ticket:** `{channel.name if channel else ticket_num}`\n"
                        f"• **Aberto por:** <@{opener_id}>\n"
                        f"• **Fechado por:** {interaction.user.mention}\n"
                        f"• **Atendido por:** {staff.mention if staff else 'Não identificado'}"
                    ),
                    color=PANEL_COLOR,
                    timestamp=discord.utils.utcnow(),
                )
                file = discord.File(io.BytesIO(transcript_bytes), filename=f"transcript-ticket-{ticket_num}.txt")
                try:
                    await log_channel.send(embed=log_embed, file=file)
                except discord.HTTPException:
                    pass

            # Envia avaliação por DM para quem abriu
            if opener_id is not None and (opener := await _resolve_user(interaction.client, interaction.guild, opener_id)):
                view = TicketRatingView(
                    bot=interaction.client,
                    guild_id=interaction.guild.id,
                    staff_id=staff.id if staff else None,
                    staff_label=staff.mention if staff else "Staff não identificado",
                    ticket_number=ticket_num,
                )
                dm_embed = discord.Embed(
                    title="⭐ Avaliação de Atendimento",
                    description=(
                        f"Seu ticket em **{interaction.guild.name}** foi encerrado.\n"
                        "Selecione uma nota de **1 a 5** estrelas para avaliar o atendimento recebido:"
                    ),
                    color=FEEDBACK_COLOR,
                )
                try:
                    dm_file = discord.File(io.BytesIO(transcript_bytes), filename=f"seu-ticket-{ticket_num}.txt")
                    await opener.send(embed=dm_embed, view=view, file=dm_file)
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
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Canal inválido.", ephemeral=True)
        await interaction.response.send_modal(AddMemberModal(interaction.channel))


class PublishPanelModal(discord.ui.Modal, title="Configurar e Publicar Painel"):
    feedback_channel_input = discord.ui.TextInput(
        label="ID do canal de feedback",
        placeholder="Ex: 123456789 (opcional)",
        required=False,
        max_length=30,
    )
    ranking_channel_input = discord.ui.TextInput(
        label="ID do canal de ranking",
        placeholder="Ex: 123456789 (opcional)",
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
            await record_ticket_claim(message.guild.id, message.author.id)
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
            title=getattr(config, "ticket_panel_title", None) or DEFAULT_PANEL_TITLE,
            description=getattr(config, "ticket_panel_desc", None) or DEFAULT_PANEL_DESC,
            color=color if color is not None else PANEL_COLOR,
        )
        footer = getattr(config, "ticket_panel_footer", None) or DEFAULT_PANEL_FOOTER
        embed.set_footer(text=footer, icon_url=getattr(config, "ticket_panel_footer_icon", None))
        if img := (image_url or runtime.get("image_url") or getattr(config, "ticket_panel_image", None)):
            embed.set_image(url=img)
        if thumb := getattr(config, "ticket_panel_thumbnail", None):
            embed.set_thumbnail(url=thumb)
        return embed

    @app_commands.command(name="ticket_painel", description="Publica o painel customizado para abrir tickets.")
    async def ticket_painel(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        modal = PublishPanelModal(self, interaction.guild.id)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="ticket_ranking", description="Envia ou atualiza o ranking da staff no canal configurado.")
    async def ticket_ranking(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        msg = await sync_ranking_channel(self.bot, interaction.guild.id, force_new=True)
        if msg:
            await interaction.response.send_message(f"Ranking atualizado em {msg.channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(embed=await build_ranking_embed(interaction.guild.id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
