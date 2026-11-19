from datetime import datetime
import discord
from discord.ext import commands
from modbot.database.models import get_guild_config


class BotProtection(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        config = await get_guild_config(guild.id)
        if not config or not config.call_log_channel_id:  # Ou o ID do seu canal de logs
            return None
        channel = guild.get_channel(config.call_log_channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.bot:
            return

        guild = member.guild
        config = await get_guild_config(guild.id)

        if not config or not getattr(config, "raid_protection_enabled", False):
            return

        added_by = None
        now = discord.utils.utcnow()

        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id and (now - entry.created_at).total_seconds() < 10:
                    added_by = entry.user
                    break
        except discord.Forbidden:
            pass

        # 1. Expulsa o bot não autorizado
        try:
            await member.kick(reason="Bot não autorizado adicionado ao servidor.")
        except discord.HTTPException:
            pass

        # 2. Remove os cargos de quem adicionou e envia o alerta formatado
        if added_by and not added_by.bot and isinstance(added_by, discord.Member):
            try:
                cargos_para_manter = [c for c in added_by.roles if c.is_default()]
                await added_by.edit(roles=cargos_para_manter, reason="Adicionou bot não autorizado.")
            except discord.HTTPException:
                pass

            log_channel = await self._get_log_channel(guild)
            if log_channel:
                timestamp_str = now.strftime("%d/%m/%Y %H:%M")
                
                descricao = (
                    "🚨 **BOT NÃO AUTORIZADO**\n"
                    "**EXPULSO**\n\n"
                    f"O usuário {added_by.mention} adicionou o bot/app **{member.name}**. O bot foi expulso e o usuário perdeu os cargos.\n\n"
                    f"{timestamp_str}"
                )

                embed = discord.Embed(description=descricao, color=discord.Color.red())
                embed.set_author(name=added_by.name, icon_url=added_by.display_avatar.url)
                
                await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BotProtection(bot))