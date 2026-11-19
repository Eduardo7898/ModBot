import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from modbot.database.models import get_guild_config


class VoiceLogs(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.joined_at: dict[tuple[int, int], datetime] = {}

    async def _get_log_channel(
        self,
        guild: discord.Guild,
    ) -> discord.TextChannel | None:
        config = await get_guild_config(guild.id)

        if not config or not config.call_log_channel_id:
            return None

        channel = guild.get_channel(config.call_log_channel_id)

        if not isinstance(channel, discord.TextChannel):
            return None

        return channel

    async def _send_log(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
        description: str,
        color: int,
    ) -> None:
        embed = discord.Embed(
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        # Cabeçalho com @nome e avatar
        embed.set_author(
            name=f"@{member.name}",
            icon_url=member.display_avatar.url,
        )

        # ID no rodapé (o timestamp aparece automaticamente ao lado dele)
        embed.set_footer(text=f"ID do usuário: {member.id}")

        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        # Ignora alterações de mute, deaf e streaming
        if before.channel == after.channel:
            return

        log_channel = await self._get_log_channel(member.guild)

        if log_channel is None:
            return

        now = discord.utils.utcnow()
        key = (member.guild.id, member.id)

        # 1. ENTROU NA CALL
        if before.channel is None and after.channel is not None:
            self.joined_at[key] = now

            description = (
                f"👉 {member.mention} entrou no canal de voz {after.channel.mention}"
            )

            await self._send_log(
                member=member,
                channel=log_channel,
                description=description,
                color=0x2ECC71,  # Verde
            )

        # 2. SAIU DA CALL
        elif before.channel is not None and after.channel is None:
            start = self.joined_at.pop(key, None)
            duration = ""

            if start is not None:
                total_seconds = int((now - start).total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                duration = (
                    f"\n⏱️ **Tempo na call:** "
                    f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                )

            description = (
                f"👉 {member.mention}\n"
                f"⛳ saiu do canal de voz {before.channel.mention}"
                f"{duration}"
            )

            await self._send_log(
                member=member,
                channel=log_channel,
                description=description,
                color=0xE74C3C,  # Vermelho
            )

        # 3. MUDOU DE CANAL (OU FOI MOVIDO)
        elif before.channel is not None and after.channel is not None:
            moved_by = None

            await asyncio.sleep(0.7)

            try:
                async for entry in member.guild.audit_logs(
                    limit=5, action=discord.AuditLogAction.member_move
                ):
                    if entry.target and entry.target.id == member.id:
                        if (now - entry.created_at).total_seconds() <= 15:
                            moved_by = entry.user
                            break
            except (discord.Forbidden, discord.HTTPException):
                pass

            if moved_by and moved_by.id != member.id:
                description = (
                    f"👉 {member.mention}\n"
                    f"🔄 foi movido de canal de voz por {moved_by.mention}\n"
                    f"🔊 **De:** {before.channel.mention} ➔ **Para:** {after.channel.mention}"
                )
            else:
                description = (
                    f"👉 {member.mention}\n"
                    f"🔄 mudou de canal de voz\n"
                    f"🔊 **De:** {before.channel.mention} ➔ **Para:** {after.channel.mention}"
                )

            await self._send_log(
                member=member,
                channel=log_channel,
                description=description,
                color=0xE67E22,  # Laranja
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceLogs(bot))