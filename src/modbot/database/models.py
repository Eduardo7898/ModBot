from tortoise import fields
from tortoise.models import Model


class GuildConfig(Model):
    """Configuração persistente de cada servidor Discord."""

    guild_id = fields.BigIntField(primary_key=True)
    master_role_id = fields.BigIntField(null=True)
    welcome_channel_id = fields.BigIntField(null=True)
    leave_channel_id = fields.BigIntField(null=True)
    antiraid_channel_id = fields.BigIntField(null=True)
    call_log_channel_id = fields.BigIntField(null=True)
    ticket_category_id = fields.BigIntField(null=True)
    ticket_support_role_id = fields.BigIntField(null=True)
    staff_log_channel_id = fields.BigIntField(null=True)
    ticket_log_channel_id = fields.BigIntField(null=True)
    raid_protection_enabled = fields.BooleanField(default=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guild_configurations"


async def get_guild_config(guild_id: int) -> GuildConfig:
    config, _ = await GuildConfig.get_or_create(guild_id=guild_id)
    return config


async def update_guild_config(guild_id: int, **kwargs) -> GuildConfig:
    allowed = {
        "master_role_id",
        "welcome_channel_id",
        "leave_channel_id",
        "antiraid_channel_id",
        "call_log_channel_id",
        "ticket_category_id",
        "ticket_support_role_id",
        "staff_log_channel_id",
        "ticket_log_channel_id",
        "raid_protection_enabled",
    }
    invalid = set(kwargs) - allowed
    if invalid:
        raise ValueError(f"Campos não permitidos: {', '.join(sorted(invalid))}")
    config = await get_guild_config(guild_id)
    for key, value in kwargs.items():
        setattr(config, key, value)
    await config.save()
    return config
