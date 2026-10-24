# MeuBot Discord

Bot modular para Discord em Python, construído com discord.py 2.x e Tortoise ORM.

## Requisitos
- Python 3.12 ou superior
- Gerenciador de pacotes [uv](https://docs.astral.sh/uv/) (recomendado) ou pip
- Aplicação e bot criados no [Discord Developer Portal](https://discord.com/developers/applications)
- Intents `Server Members Intent` e `Message Content Intent` habilitados no portal
- Permissões recomendadas: View Channels, Send Messages, Embed Links, Read Message History, Manage Channels, Kick Members e Manage Roles

## Instalação e Execução

### Usando uv (Recomendado)
1. Instale as dependências:
   ```bash
   uv sync
   ```
2. Configure o token do Discord (criptografado com segurança em `~/.modbot/config.enc`, compatível inclusive com mobile/Termux):
   ```bash
   uv run modbot config
   ```
   *(Ou passe diretamente via flag: `uv run modbot config --token SEU_TOKEN`)*
3. Inicie o bot:
   ```bash
   uv run modbot
   ```

### Atualização do Pacote
Para atualizar o ModBot com a versão mais recente diretamente do repositório GitHub:
```bash
uv run modbot update
```

### Comandos da CLI (`modbot`)
- `uv run modbot`: Inicia o bot do Discord.
- `uv run modbot config`: Solicita e salva o token criptografado.
  - `--show` (`-s`): Exibe o status da configuração atual do token.
  - `--clear` (`-c`): Remove o token armazenado.
  - `--token <valor>` (`-t`): Define o token diretamente sem prompt interativo.
- `uv run modbot update`: Atualiza o pacote com a versão mais recente do GitHub via uv/pip.
- `uv run modbot --help`: Exibe a ajuda geral da CLI.

### Usando ambiente virtual padrão (venv)
1. Crie e ative o ambiente virtual:
   - Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`
   - Windows: `py -m venv .venv && .venv\Scripts\activate`
2. Instale o pacote no modo editável:
   ```bash
   pip install -e .
   ```
3. Configure e execute:
   ```bash
   modbot config
   modbot
   ```

O banco SQLite `db.sqlite3` será criado automaticamente. Nunca compartilhe o token do seu bot.

## Comandos Disponíveis
- `/sync`: sincroniza os comandos de barra com o Discord (apenas Administradores ou Cargo Master). Use `escopo: servidor_atual` para sincronização instantânea de testes.
- `/setup`: administrador escolhe o Cargo Master do servidor.
- `/config_canal`: configura boas-vindas, saídas e canais de logs.
- `/config_tickets`: configura a categoria e o cargo de suporte dos tickets.
- `/ticket_painel`: publica o painel de abertura de tickets.
- `/gerenciamento`: métricas do bot e painel administrativo.
- `/cargo`: adiciona ou remove um cargo de um membro respeitando a hierarquia.
- `/expulsar`: expulsa um membro com checagem de permissão e hierarquia.
- `/protecao`: ativa ou desativa o anti-raid conservador para contenção de novos bots.
- `/ticket_adicionar`: concede acesso a um membro ao canal do ticket.

## Segurança e Observações
- O Cargo Master é uma autorização configurável do bot; a hierarquia e permissões nativas do Discord continuam valendo.
- O bot precisa ter permissão de gerenciar canais e cargos, e o seu cargo deve estar posicionado acima dos cargos que gerencia.
- Os botões dos tickets permanecem funcionais mesmo se o bot for reiniciado.
- O Anti-Raid opera de forma conservadora: verifica audit logs antes de agir para evitar falsos positivos.
