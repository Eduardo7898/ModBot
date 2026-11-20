from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import timedelta

import discord
from discord.ext import commands

from modbot.database.models import get_guild_config

logger = logging.getLogger(__name__)


@dataclass
class SpamState:
    messages: deque[tuple[float, str, int, bool]] = field(default_factory=deque)
    punished_until: float = 0.0


class BotProtection(commands.Cog):
    TIMEOUT_MINUTES = 30

    REPEAT_LIMIT = 5
    REPEAT_WINDOW = 8

    MESSAGE_LIMIT = 7
    MESSAGE_WINDOW = 8

    MENTION_LIMIT_PER_MESSAGE = 5
    MENTION_LIMIT_TOTAL = 8
    MENTION_LIMIT_WINDOW = 10

    LINK_LIMIT = 3
    LINK_WINDOW = 10

    MAX_USERS_CACHE = 5000
    MAX_CONFIG_CACHE = 500
    CONFIG_CACHE_TTL = 15
    CACHE_WINDOW = 15

    LINK_REGEX = re.compile(
        r"(https?://|www\.|discord\.gg/|discord(?:app)?\.com/invite/)",
        re.IGNORECASE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.spam_cache: OrderedDict[tuple[int, int], SpamState] = OrderedDict()
        self.config_cache: OrderedDict[int, tuple[float, object]] = OrderedDict()
        self.config_locks: dict[int, asyncio.Lock] = {}

    def invalidate_guild_cache(self, guild_id: int) -> None:
        self.config_cache.pop(guild_id, None)

    @staticmethod
    def _touch_lru(cache: OrderedDict, key: object, max_size: int) -> None:
        cache.move_to_end(key)
        while len(cache) > max_size:
            cache.popitem(last=False)

    async def _get_config(self, guild_id: int):
        now = time.monotonic()
        cached = self.config_cache.get(guild_id)
        if cached and now - cached[0] < self.CONFIG_CACHE_TTL:
            self._touch_lru(self.config_cache, guild_id, self.MAX_CONFIG_CACHE)
            return cached[1]

        lock = self.config_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self.config_cache.get(guild_id)
            if cached and now - cached[0] < self.CONFIG_CACHE_TTL:
                self._touch_lru(self.config_cache, guild_id, self.MAX_CONFIG_CACHE)
                return cached[1]

            try:
                config = await get_guild_config(guild_id)
            except Exception:
                logger.exception("Erro ao carregar configuração do servidor %s", guild_id)
                return None

            self.config_cache[guild_id] = (now, config)
            self._touch_lru(self.config_cache, guild_id, self.MAX_CONFIG_CACHE)
            return config

    async def _get_log_channel(
        self,
        guild: discord.Guild,
        *,
        prefer_antiraid: bool = False,
    ) -> discord.TextChannel | None:
        config = await self._get_config(guild.id)
        if not config:
            return None

        primary, fallback = (
            ("antiraid_channel_id", "call_log_channel_id")
            if prefer_antiraid
            else ("call_log_channel_id", "antiraid_channel_id")
        )
        channel_id = getattr(config, primary, None) or getattr(config, fallback, None)
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    def _get_spam_state(self, guild_id: int, user_id: int) -> SpamState:
        key = (guild_id, user_id)
        state = self.spam_cache.setdefault(key, SpamState())
        self._touch_lru(self.spam_cache, key, self.MAX_USERS_CACHE)
        return state

    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        *,
        prefer_antiraid: bool = False,
    ) -> None:
        try:
            channel = await self._get_log_channel(guild, prefer_antiraid=prefer_antiraid)
            if channel:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            logger.warning("Sem permissão para enviar logs no servidor %s", guild.id)
        except discord.HTTPException:
            logger.exception("Erro ao enviar log no servidor %s", guild.id)

    # ==========================================
    # ANTI-RAID
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.bot:
            return

        guild = member.guild
        config = await self._get_config(guild.id)
        if not config or not getattr(config, "raid_protection_enabled", False):
            return

        added_by = None
        now = discord.utils.utcnow()

        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                if (
                    entry.target
                    and entry.target.id == member.id
                    and (now - entry.created_at).total_seconds() < 10
                ):
                    added_by = entry.user
                    break
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            logger.exception("Erro ao consultar audit logs do servidor %s", guild.id)

        try:
            await member.kick(reason="Bot não autorizado adicionado ao servidor.")
        except discord.Forbidden:
            logger.warning("Sem permissão para expulsar o bot %s no servidor %s", member.id, guild.id)
        except discord.HTTPException:
            logger.exception("Erro ao expulsar o bot %s", member.id)

        if not (added_by and not added_by.bot and isinstance(added_by, discord.Member)):
            return

        try:
            roles = [role for role in added_by.roles if role.is_default()]
            await added_by.edit(roles=roles, reason="Adicionou bot não autorizado.")
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            logger.exception("Erro ao remover cargos do usuário %s", added_by.id)

        embed = discord.Embed(
            description=(
                "🚨 **BOT NÃO AUTORIZADO**\n"
                "**EXPULSO**\n\n"
                f"O usuário {added_by.mention} adicionou "
                f"o bot/app **{member.name}**. "
                "O bot foi expulso e o usuário perdeu os cargos.\n\n"
                f"{now.strftime('%d/%m/%Y %H:%M')}"
            ),
            color=discord.Color.red(),
        )
        embed.set_author(name=added_by.name, icon_url=added_by.display_avatar.url)
        await self._send_log(guild, embed, prefer_antiraid=True)

    # ==========================================
    # ANTI-SPAM
    # ==========================================

    @staticmethod
    def _get_content_hash(content: str) -> str:
        normalized = " ".join(content.casefold().split())
        return hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).hexdigest()

    def _check_spam(
        self,
        state: SpamState,
        content: str,
        mention_count: int,
        has_link: bool,
        now: float,
    ) -> str | None:
        messages = state.messages
        while messages and now - messages[0][0] > self.CACHE_WINDOW:
            messages.popleft()

        content_hash = self._get_content_hash(content)
        messages.append((now, content_hash, mention_count, has_link))

        if sum(1 for ts, *_ in messages if now - ts <= self.MESSAGE_WINDOW) >= self.MESSAGE_LIMIT:
            return "Envio excessivo de mensagens."

        if (
            sum(
                1
                for ts, msg_hash, *_ in messages
                if now - ts <= self.REPEAT_WINDOW and msg_hash == content_hash
            )
            >= self.REPEAT_LIMIT
        ):
            return "Envio de mensagens repetidas."

        if mention_count >= self.MENTION_LIMIT_PER_MESSAGE:
            return "Excesso de menções em uma mensagem."

        if (
            sum(mentions for ts, _, mentions, _ in messages if now - ts <= self.MENTION_LIMIT_WINDOW)
            >= self.MENTION_LIMIT_TOTAL
        ):
            return "Envio excessivo de menções."

        if (
            sum(1 for ts, _, _, linked in messages if now - ts <= self.LINK_WINDOW and linked)
            >= self.LINK_LIMIT
        ):
            return "Envio excessivo de links."

        return None

    async def _apply_timeout(
        self,
        message: discord.Message,
        state: SpamState,
        reason: str,
    ) -> None:
        member = message.author
        guild = message.guild
        if not isinstance(member, discord.Member) or guild is None:
            return

        try:
            await member.timeout(
                timedelta(minutes=self.TIMEOUT_MINUTES),
                reason=f"Anti-Spam: {reason}",
            )
        except discord.Forbidden:
            logger.warning(
                "Não foi possível aplicar timeout em %s no servidor %s: "
                "sem permissão ou hierarquia insuficiente.",
                member.id,
                guild.id,
            )
            return
        except discord.HTTPException:
            logger.exception("Erro ao aplicar timeout em %s", member.id)
            return

        state.punished_until = time.monotonic() + self.TIMEOUT_MINUTES * 60
        state.messages.clear()

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        except discord.HTTPException:
            logger.exception("Erro ao apagar mensagem de spam do usuário %s", member.id)

        embed = discord.Embed(
            title="🚨 Anti-Spam | Usuário punido",
            description=(
                f"**Usuário:** {member.mention}\n"
                f"**ID:** `{member.id}`\n"
                f"**Motivo:** {reason}\n"
                f"**Punição:** Timeout de {self.TIMEOUT_MINUTES} minutos"
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or message.author.bot
            or message.webhook_id
            or not isinstance(message.author, discord.Member)
            or not message.content
            or message.author.guild_permissions.moderate_members
        ):
            return

        config = await self._get_config(message.guild.id)
        if config is not None and not getattr(config, "anti_spam_enabled", True):
            return

        now = time.monotonic()
        state = self._get_spam_state(message.guild.id, message.author.id)
        if state.punished_until > now:
            return

        mention_count = (
            len(message.mentions)
            + len(message.role_mentions)
            + int(message.mention_everyone)
        )
        has_link = bool(self.LINK_REGEX.search(message.content))
        reason = self._check_spam(state, message.content, mention_count, has_link, now)
        if reason:
            await self._apply_timeout(message, state, reason)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BotProtection(bot))