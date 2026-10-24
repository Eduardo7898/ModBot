import discord
from discord.ext import commands
from src.models import get_guild_config

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await get_guild_config(member.guild.id)
        if member.bot:
            await self._handle_new_bot(member, config)
            return
        channel = member.guild.get_channel(config.welcome_channel_id) if config.welcome_channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="Bem-vindo(a)!",
            description=f"{member.mention} entrou no servidor.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Conta criada em", value=discord.utils.format_dt(member.created_at, style="F"), inline=False)
        embed.add_field(name="Membros", value=str(member.guild.member_count or "desconhecido"))
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    async def _handle_new_bot(self, member, config):
        """Contenção conservadora: remove bots recém-adicionados apenas quando o autor não pode ser validado.
        Não remove cargos de pessoas automaticamente; isso pode causar danos graves em caso de falso positivo.
        """
        if not config.raid_protection_enabled:
            return
        log_channel = member.guild.get_channel(config.antiraid_channel_id) if config.antiraid_channel_id else None
        try:
            async for entry in member.guild.audit_logs(limit=8, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age > 30:
                        continue
                    actor = entry.user
                    if actor and (actor.id == member.guild.owner_id or
                                  (isinstance(actor, discord.Member) and
                                   (actor.guild_permissions.administrator or
                                    (config.master_role_id and any(r.id == config.master_role_id for r in actor.roles))))):
                        return
                    # Se o autor não for autorizado, tenta expulsar o bot somente se o bot tiver permissão.
                    if member.guild.me and member.guild.me.guild_permissions.kick_members:
                        await member.kick(reason="Anti-Raid: bot adicionado por usuário não autorizado")
                        if isinstance(log_channel, discord.TextChannel):
                            await log_channel.send(
                                f"🛡️ Bot não autorizado expulso: {member} (`{member.id}`). "
                                f"Autor identificado: {actor} (`{actor.id}`) se disponível."
                            )
                    return
        except (discord.Forbidden, discord.HTTPException):
            if isinstance(log_channel, discord.TextChannel):
                await log_channel.send("⚠️ Não foi possível verificar os Audit Logs do Discord. Verifique as permissões do bot.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        config = await get_guild_config(member.guild.id)
        channel = member.guild.get_channel(config.leave_channel_id) if config.leave_channel_id else None
        if isinstance(channel, discord.TextChannel):
            await channel.send(
                f"👋 **{discord.utils.escape_markdown(member.display_name)}** saiu do servidor. "
                f"Membros restantes: **{member.guild.member_count or 'desconhecido'}**."
            )

async def setup(bot):
    await bot.add_cog(Welcome(bot))
