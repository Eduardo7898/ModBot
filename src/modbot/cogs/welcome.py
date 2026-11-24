import discord
from discord.ext import commands

from modbot.cogs.management import get_welcome_visual_settings
from modbot.database.models import get_guild_config


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        config = await get_guild_config(member.guild.id)
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
