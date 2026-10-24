import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
from tortoise import Tortoise

from src.database import TORTOISE_ORM

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não definido. Copie .env.example para .env e configure o token.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True  # Ative também este intent no Developer Portal.

class MeuBot(commands.Bot):
    async def setup_hook(self):
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas(safe=True)

        for path in sorted((BASE_DIR / "src" / "cogs").glob("*.py")):
            if path.name.startswith("_"):
                continue
            extension = f"src.cogs.{path.stem}"
            await self.load_extension(extension)
            logging.info("Cog carregado: %s", extension)

        # Sincroniza comandos slash globalmente. A propagação pode levar algum tempo.
        await self.tree.sync()

    async def close(self):
        try:
            await Tortoise.close_connections()
        finally:
            await super().close()

bot = MeuBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logging.info("Conectado como %s (ID: %s)", bot.user, bot.user.id if bot.user else "desconhecido")

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
