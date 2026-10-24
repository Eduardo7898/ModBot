from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
from typing import Annotated, Optional

import discord
import typer

from modbot.bot import ModBot
from modbot.utils.crypto import (
    CONFIG_FILE,
    has_token,
    load_token,
    remove_token,
    save_token,
)

_log = logging.getLogger("modbot")

app = typer.Typer(
    name="modbot",
    help="ModBot - Bot modular para Discord.",
    no_args_is_help=False,
)

REPO_URL = "https://github.com/vinifreittas/ModBot.git"


def start_bot() -> None:
    """Verifica credenciais, configura logs e inicia o bot diretamente."""
    token = load_token()
    if not token:
        typer.secho(
            "❌ Nenhum token do Discord encontrado ou configurado.",
            fg=typer.colors.RED,
            bold=True,
        )
        typer.echo(
            "Execute o comando abaixo para configurar seu token:\n"
            "  uv run modbot config"
        )
        raise typer.Exit(code=1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    typer.secho("🚀 Iniciando ModBot...", fg=typer.colors.GREEN, bold=True)

    async def _runner() -> None:
        async with ModBot() as bot:
            await bot.start(token)

    try:
        asyncio.run(_runner())
    except discord.errors.LoginFailure:
        _log.error(
            "Token do Discord inválido ou rejeitado pela API. "
            "Execute 'uv run modbot config' para reconfigurar."
        )
    except KeyboardInterrupt:
        _log.info("ModBot interrompido pelo usuário.")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Ponto de entrada padrão.

    Se nenhum subcomando for passado, inicia o bot.
    """
    if ctx.invoked_subcommand is None:
        start_bot()


@app.command(name="start", help="Inicia o bot do Discord.")
def start_cmd() -> None:
    """Inicia explicitamente o ModBot."""
    start_bot()


@app.command(name="config", help="Configura e gerencia o token do Discord.")
def config_cmd(
    token: Annotated[
        Optional[str],
        typer.Option(
            "--token",
            "-t",
            help="Define o token diretamente via argumento.",
        ),
    ] = None,
    show: Annotated[
        bool,
        typer.Option(
            "--show",
            "-s",
            help="Exibe o status atual do token configurado.",
        ),
    ] = False,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            "-c",
            help="Remove o token configurado atualmente.",
        ),
    ] = False,
) -> None:
    """Configura e salva o token criptografado em ~/.modbot/config.enc."""
    if clear:
        if remove_token():
            typer.secho(
                "🗑️ Token removido com sucesso de ~/.modbot/config.enc.",
                fg=typer.colors.YELLOW,
            )
        else:
            typer.echo("ℹ️ Nenhum token configurado para remover.")
        return

    if show:
        if has_token():
            current = load_token()
            masked = (
                f"{current[:6]}...{current[-4:]}"
                if current and len(current) > 10
                else "******"
            )
            typer.secho(" Configuração encontrada:", fg=typer.colors.GREEN, bold=True)
            typer.echo(f"  Arquivo: {CONFIG_FILE}")
            typer.echo(f"  Token:   {masked}")
        else:
            typer.secho(
                "❌ Nenhum token configurado no momento.",
                fg=typer.colors.RED,
            )
            typer.echo("Use 'uv run modbot config' para definir um.")
        return

    # Definir novo token
    if not token:
        typer.secho("Configuração do Token do Discord", fg=typer.colors.CYAN, bold=True)
        typer.echo(
            "O token será criptografado e salvo com segurança em ~/.modbot/config.enc."
        )
        token = typer.prompt("Cole o token do seu bot", hide_input=True)

    token = token.strip()
    if not token:
        typer.secho("❌ O token não pode ser vazio.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        save_token(token)
        typer.secho(
            " Token salvo e criptografado com sucesso em ~/.modbot/config.enc!",
            fg=typer.colors.GREEN,
            bold=True,
        )
        typer.echo("Você já pode iniciar o bot com: uv run modbot")
    except Exception as exc:
        typer.secho(
            f"❌ Falha ao salvar token: {exc}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc


@app.command(name="update", help="Atualiza o ModBot com a última versão do GitHub.")
def update_cmd(
    repo: Annotated[
        str,
        typer.Option(
            "--repo",
            "-r",
            help="URL do repositório Git para atualização.",
        ),
    ] = REPO_URL,
) -> None:
    """Atualiza o pacote modbot via UV ou Pip direto do repositório Git."""
    typer.secho(
        f"🔄 Atualizando ModBot a partir de {repo}...",
        fg=typer.colors.CYAN,
        bold=True,
    )

    uv_path = shutil.which("uv")
    if uv_path:
        cmd = [uv_path, "pip", "install", "--upgrade", f"git+{repo}"]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", f"git+{repo}"]

    try:
        subprocess.run(cmd, check=True)
        typer.secho(
            " ModBot atualizado com sucesso!",
            fg=typer.colors.GREEN,
            bold=True,
        )
    except subprocess.CalledProcessError as err:
        typer.secho(
            f"❌ Falha ao atualizar ModBot: comando retornou código {err.returncode}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=err.returncode) from err
    except Exception as exc:
        typer.secho(
            f"❌ Erro inesperado durante a atualização: {exc}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
