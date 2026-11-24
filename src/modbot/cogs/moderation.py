import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import get_guild_config, update_guild_config
from modbot.utils.permissions import require_master


class Moderation(commands.Cog):
    """Cog de moderação e proteção Anti-Raid unificada."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        config = await get_guild_config(guild.id)
        if not config or not config.antiraid_channel_id:
            return None
        channel = guild.get_channel(config.antiraid_channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.bot:
            return

        guild = member.guild
        config = await get_guild_config(guild.id)

        if not config or not getattr(config, "raid_protection_enabled", True):
            return

        added_by = None
        now = discord.utils.utcnow()

        try:
            async for entry in guild.audit_logs(limit=6, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    if (now - entry.created_at).total_seconds() <= 60:
                        added_by = entry.user
                        break
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Verifica se o autor da adição possui autorização (Dono, Admin ou Cargo Master)
        if added_by:
            if added_by.id == guild.owner_id:
                return

            if isinstance(added_by, discord.Member):
                if added_by.guild_permissions.administrator:
                    return
                if config.master_role_id and any(r.id == config.master_role_id for r in added_by.roles):
                    return

        # 1. Expulsa o bot não autorizado
        if guild.me and guild.me.guild_permissions.kick_members:
            try:
                await member.kick(reason="Anti-Raid: Bot adicionado sem autorização da administração.")
            except discord.HTTPException:
                pass

        # 2. Executa punição em quem adicionou, se configurado
        punish_mode = getattr(config, "antiraid_punish_mode", "strip_roles")
        roles_stripped = False

        if added_by and not added_by.bot and isinstance(added_by, discord.Member):
            if punish_mode == "strip_roles" and guild.me and guild.me.guild_permissions.manage_roles:
                try:
                    cargos_para_manter = [c for c in added_by.roles if c.is_default()]
                    await added_by.edit(roles=cargos_para_manter, reason="Anti-Raid: Adicionou bot sem autorização.")
                    roles_stripped = True
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # 3. Envia o alerta para o canal de logs Anti-Raid
        log_channel = await self._get_log_channel(guild)
        if log_channel:
            timestamp_str = now.strftime("%d/%m/%Y %H:%M")
            adder_text = added_by.mention if added_by else "Não identificado (verifique Audit Logs)"
            punish_text = "O usuário perdeu seus cargos." if roles_stripped else "Nenhum cargo foi retirado (Modo apenas expulsar)."

            descricao = (
                "🚨 **BOT NÃO AUTORIZADO DETECTADO**\n"
                "🛡️ **Ação Anti-Raid Executada**\n\n"
                f"• **Bot Expulso:** `{member.name}` (`{member.id}`)\n"
                f"• **Adicionado por:** {adder_text}\n"
                f"• **Punição:** {punish_text}\n\n"
                f"🕒 {timestamp_str}"
            )

            embed = discord.Embed(description=descricao, color=discord.Color.red(), timestamp=now)
            if added_by and hasattr(added_by, "display_avatar"):
                embed.set_author(name=f"Alerta Anti-Raid | {added_by.name}", icon_url=added_by.display_avatar.url)
            else:
                embed.set_author(name="Alerta Anti-Raid")

            try:
                await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass

    @app_commands.command(name="protecao", description="Configura a proteção Anti-Raid do servidor.")
    @app_commands.describe(
        ativado="Ativa ou desativa a proteção Anti-Raid",
        modo_punicao="Modo de punição para quem adiciona bots não autorizados",
    )
    @app_commands.choices(
        modo_punicao=[
            app_commands.Choice(name="Expulsar bot e retirar cargos do autor", value="strip_roles"),
            app_commands.Choice(name="Apenas expulsar o bot (sem retirar cargos)", value="kick_only"),
        ]
    )
    async def protecao(
        self,
        interaction: discord.Interaction,
        ativado: bool | None = None,
        modo_punicao: app_commands.Choice[str] | None = None,
    ) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return

        config = await get_guild_config(interaction.guild.id)
        updates: dict[str, object] = {}

        if ativado is not None:
            updates["raid_protection_enabled"] = ativado
        if modo_punicao is not None:
            updates["antiraid_punish_mode"] = modo_punicao.value

        if updates:
            config = await update_guild_config(interaction.guild.id, **updates)

        status_str = "🟢 Ativada" if config.raid_protection_enabled else "🔴 Desativada"
        punish_desc = (
            "Expulsar bot e retirar cargos"
            if config.antiraid_punish_mode == "strip_roles"
            else "Apenas expulsar o bot"
        )

        embed = discord.Embed(
            title="🛡️ Configurações de Proteção Anti-Raid",
            color=discord.Color.green() if config.raid_protection_enabled else discord.Color.red(),
        )
        embed.add_field(name="Status da Proteção", value=status_str, inline=True)
        embed.add_field(name="Modo de Punição", value=punish_desc, inline=True)
        canal_log = f"<#{config.antiraid_channel_id}>" if config.antiraid_channel_id else "`Não configurado`"
        embed.add_field(name="Canal de Alertas", value=canal_log, inline=False)
        embed.set_footer(text="Use /gerenciamento para configurar os canais de logs.")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
