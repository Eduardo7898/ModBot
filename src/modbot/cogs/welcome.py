import discord
from discord.ext import commands

from modbot.cogs.management import get_welcome_visual_settings
from modbot.database.models import get_guild_config


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        config = await get_guild_config(member.guild.id)
        if member.bot:
            await self._handle_new_bot(member, config)
            return

        channel = (
            member.guild.get_channel(config.welcome_channel_id)
            if config.welcome_channel_id
            else None
        )
        if not isinstance(channel, discord.TextChannel):
            return

        welcome_color, welcome_image = get_welcome_visual_settings(
            member.guild.id, config
        )
        member_count = member.guild.member_count or "?"

        embed = discord.Embed(
            title="「 B E M - V I N D O 」",
            description=(
                f"**{member.mention}** chegou ao baile! 🎉\n"
                f"📊 Agora somos **{member_count}** cidadãos."
            ),
            color=welcome_color,
            timestamp=discord.utils.utcnow(),
        )

        embed.set_author(
            name=member.guild.name,
            icon_url=member.guild.icon.url if member.guild.icon else None,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="👤 Usuário",
            value=member.mention,
            inline=True,
        )
        embed.add_field(
            name="📅 Conta criada em",
            value=discord.utils.format_dt(member.created_at, style="D"),
            inline=True,
        )
        embed.add_field(
            name="🤖 Bot",
            value="Sim" if member.bot else "Não",
            inline=True,
        )

        if welcome_image:
            embed.set_image(url=welcome_image)

        embed.set_footer(text=f"ID: {member.id}")

        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        )

    async def _handle_new_bot(self, member: discord.Member, config) -> None:
        """Contenção conservadora: remove bots recém-adicionados apenas quando o autor
        não pode ser validado. Não remove cargos de pessoas automaticamente;
        isso pode causar danos graves em caso de falso positivo.
        """
        if not config.raid_protection_enabled:
            return
        log_channel = (
            member.guild.get_channel(config.antiraid_channel_id)
            if config.antiraid_channel_id
            else None
        )
        try:
            async for entry in member.guild.audit_logs(
                limit=8, action=discord.AuditLogAction.bot_add
            ):
                if entry.target and entry.target.id == member.id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age > 30:
                        continue
                    actor = entry.user
                    if actor and (
                        actor.id == member.guild.owner_id
                        or (
                            isinstance(actor, discord.Member)
                            and (
                                actor.guild_permissions.administrator
                                or (
                                    config.master_role_id
                                    and any(
                                        r.id == config.master_role_id
                                        for r in actor.roles
                                    )
                                )
                            )
                        )
                    ):
                        return
                    if (
                        member.guild.me
                        and member.guild.me.guild_permissions.kick_members
                    ):
                        await member.kick(
                            reason=(
                                "Anti-Raid: bot adicionado por usuário não autorizado"
                            )
                        )
                        if isinstance(log_channel, discord.TextChannel):
                            await log_channel.send(
                                f"🛡️ Bot não autorizado expulso: {member} "
                                f"(`{member.id}`). Autor identificado: {actor} "
                                f"(`{actor.id}`) se disponível."
                            )
                    return
        except (discord.Forbidden, discord.HTTPException):
            if isinstance(log_channel, discord.TextChannel):
                await log_channel.send(
                    "⚠️ Não foi possível verificar os Audit Logs do Discord. "
                    "Verifique as permissões do bot."
                )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        config = await get_guild_config(member.guild.id)
        channel = (
            member.guild.get_channel(config.leave_channel_id)
            if config.leave_channel_id
            else None
        )
        if isinstance(channel, discord.TextChannel):
            escaped_name = discord.utils.escape_markdown(member.display_name)
            member_count = member.guild.member_count or "desconhecido"
            await channel.send(
                f"👋 **{escaped_name}** saiu do servidor. "
                f"Membros restantes: **{member_count}**."
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
