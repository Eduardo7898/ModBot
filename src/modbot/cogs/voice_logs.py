import discord
from discord.ext import commands

from modbot.database.models import get_guild_config


class VoiceLogs(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.joined_at: dict[tuple[int, int], discord.utils.MISSING] = {}

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        config = await get_guild_config(member.guild.id)
        channel = (
            member.guild.get_channel(config.call_log_channel_id)
            if config.call_log_channel_id
            else None
        )
        if not isinstance(channel, discord.TextChannel):
            return

        now = discord.utils.utcnow()
        if before.channel is None and after.channel is not None:
            self.joined_at[(member.guild.id, member.id)] = now
            time_str = discord.utils.format_dt(now, style="t")
            message = (
                f"🟢 {member.mention} entrou em {after.channel.mention} às {time_str}."
            )
        elif before.channel is not None and after.channel is None:
            start = self.joined_at.pop((member.guild.id, member.id), None)
            duration = (
                f" Duração aproximada: {int((now - start).total_seconds())} segundos."
                if start
                else ""
            )
            time_str = discord.utils.format_dt(now, style="t")
            message = (
                f"🔴 {member.mention} saiu de **{before.channel.name}** "
                f"às {time_str}.{duration}"
            )
        elif before.channel != after.channel:
            message = (
                f"🔁 {member.mention} mudou de **{before.channel.name}** "
                f"para **{after.channel.name}**."
            )
        else:
            return
        await channel.send(message, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceLogs(bot))
