import discord
from discord.ext import commands

from modbot.models import get_guild_config


class VoiceLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.joined_at = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
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
            message = f"🟢 {member.mention} entrou em {after.channel.mention} às {discord.utils.format_dt(now, style='t')}."
        elif before.channel is not None and after.channel is None:
            start = self.joined_at.pop((member.guild.id, member.id), None)
            duration = (
                f" Duração aproximada: {int((now - start).total_seconds())} segundos."
                if start
                else ""
            )
            message = f"🔴 {member.mention} saiu de **{before.channel.name}** às {discord.utils.format_dt(now, style='t')}.{duration}"
        elif before.channel != after.channel:
            message = f"🔁 {member.mention} mudou de **{before.channel.name}** para **{after.channel.name}**."
        else:
            return
        await channel.send(message, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(VoiceLogs(bot))
