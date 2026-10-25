"""Módulo principal do bot do Discord (ModBot).

Gerencia a classe ModBot, intents, carregamento de cogs, inicialização do Tortoise ORM
e encerramento limpo das conexões.
"""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands
from tortoise import Tortoise

from modbot.database import TORTOISE_ORM

_log = logging.getLogger(__name__)


class ModBot(commands.Bot):
    """Bot principal do ModBot.

    Gerencia intents, carregamento de cogs, eventos e encerramento.
    """

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)

    
    async def setup_hook(self) -> None:
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas(safe=True)

        cogs_dir = Path(__file__).parent / "cogs"

        for path in sorted(cogs_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue

            extension = f"modbot.cogs.{path.stem}"
            await self.load_extension(extension)
            _log.info("Cog carregado: %s", extension)

        # Sincroniza os comandos de barra com o Discord
        synced = await self.tree.sync()
        _log.info(
            "Sincronização concluída: %s comandos de aplicação registrados.",
            len(synced),
        )


    async def on_ready(self) -> None:
        _log.info(
            "Conectado como %s (ID: %s)",
            self.user,
            self.user.id if self.user else "desconhecido",
        )

    async def close(self) -> None:
        try:
            if getattr(Tortoise, "_inited", False):
                await Tortoise.close_connections()
        except Exception as exc:
            _log.warning("Falha ao fechar conexões com banco: %s", exc)
        finally:
            await super().close()
