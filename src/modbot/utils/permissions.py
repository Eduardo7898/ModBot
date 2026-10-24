import discord
from discord import app_commands

from modbot.database.models import get_guild_config


async def is_master(interaction: discord.Interaction) -> bool:
    """Retorna True se o usuário é administrador ou possui o Cargo Master."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    config = await get_guild_config(interaction.guild.id)
    return bool(
        config.master_role_id
        and any(role.id == config.master_role_id for role in interaction.user.roles)
    )


async def require_master(interaction: discord.Interaction) -> bool:
    """Verifica permissão e envia mensagem de erro se não autorizado. Retorna bool."""
    if await is_master(interaction):
        return True
    message = "Você precisa do Cargo Master configurado ou da permissão Administrador."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return False


def master_check() -> app_commands.check:
    """Decorator de verificação de permissão para comandos de app."""
    async def predicate(interaction: discord.Interaction) -> bool:
        return await is_master(interaction)

    return app_commands.check(predicate)
