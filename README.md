<div align="center">

# 🤖 ModBot

**Bot modular para Discord com arquitetura assíncrona, CLI moderna e criptografia pura em Python.**

Construído com [discord.py 2.x](https://github.com/Rapptz/discord.py) e [Tortoise ORM](https://tortoise.github.io/), projetado para máxima performance, segurança e portabilidade multiplataforma.

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.4%2B-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![Tortoise ORM](https://img.shields.io/badge/ORM-Tortoise--ORM-green)](https://tortoise.github.io/)
[![Package Manager](https://img.shields.io/badge/gerenciador-uv-purple?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![Plataformas](https://img.shields.io/badge/plataforma-Linux%20%7C%20Windows%20%7C%20macOS%20%7C%20Termux-orange)](https://github.com/vinifreittas/ModBot)

---

[Visão Geral](#-visão-geral) •
[Instalação Rápida](#-instalação-rápida) •
[CLI ModBot](#-comandos-da-cli) •
[Comandos Slash](#-comandos-disponíveis-slash-commands) •
[Arquitetura](#-estrutura-do-projeto) •
[Segurança](#-segurança-e-permissões)

</div>

---

## 🌟 Visão Geral

O **ModBot** é uma solução completa para administração, segurança e engajamento em servidores Discord. Ele combina:

- 🛡️ **Segurança e Anti-Raid Conservador**: Prevenção ativa contra bots maliciosos sem falsos positivos.
- 🎫 **Sistema de Tickets Dinâmico**: Painéis interativos com botões persistentes e controle de atendimento.
- 🎙️ **Logs em Tempo Real**: Monitoramento detalhado de canais de voz, entradas, saídas e ações administrativas.
- 🔐 **Criptografia Zero-C-Dependencies**: Armazenamento seguro de credenciais via criptografia pura em Python, garantindo compatibilidade **100% nativa em Android/Termux, Linux, Windows e macOS**.
- ⚡ **CLI Poderosa com Typer**: Gerenciamento de credenciais, atualização direta do GitHub e inicialização em um único comando.

---

## 🚀 Instalação Rápida

### Pré-requisitos
- **Python 3.12** ou superior instalado.
- Gerenciador de pacotes [uv](https://docs.astral.sh/uv/) (*altamente recomendado*) ou `pip`.
- Bot e aplicação criados no [Discord Developer Portal](https://discord.com/developers/applications).
- Intents obrigatórios ativados no portal:
  - `Server Members Intent`
  - `Message Content Intent`

---

### Passo a Passo com `uv`

```bash
# 1. Clone o repositório
git clone https://github.com/vinifreittas/ModBot.git
cd ModBot

# 2. Instale as dependências sincronizadas
uv sync

# 3. Configure seu token do Discord de forma segura
uv run modbot config

# 4. Inicie o ModBot!
uv run modbot
```

> [!TIP]
> O token e o banco SQLite são salvos centralmente em `~/.modbot/`. Isso significa que você pode executar `uv run modbot` a partir de qualquer pasta sem perder dados ou configurações!

---

### Alternativa: Usando `venv` tradicional

<details>
<summary><b>Clique para ver as instruções com venv e pip</b></summary>

```bash
# 1. Crie e ative o ambiente virtual
# Linux/macOS / Termux:
python3 -m venv .venv && source .venv/bin/activate

# Windows:
py -m venv .venv && .venv\Scripts\activate

# 2. Instale o pacote em modo editável
pip install -e .

# 3. Configure e execute
modbot config
modbot
```
</details>

---

## 💻 Comandos da CLI

A CLI do ModBot oferece ergonomia e controle total sobre a aplicação:

```bash
# Iniciação rápida (comando padrão)
uv run modbot
```

| Comando | Descrição |
| :--- | :--- |
| `uv run modbot` | Inicia o bot do Discord diretamente. |
| `uv run modbot start` | Inicia explicitamente o bot. |
| `uv run modbot config` | Solicita o token de forma segura (input oculto sem eco). |
| `uv run modbot config --show` | Exibe se o token está configurado e o arquivo de destino (mascarado). |
| `uv run modbot config --clear` | Remove o token armazenado com segurança. |
| `uv run modbot config -t <TOKEN>` | Define o token diretamente via flag. |
| `uv run modbot update` | Atualiza o pacote com a última versão do GitHub via `uv`/`pip`. |
| `uv run modbot --help` | Exibe o menu interativo com todas as opções e ajuda. |

---

## 📂 Armazenamento e Criptografia Portável

Todos os dados persistentes do ModBot ficam centralizados no diretório de usuário `~/.modbot/`:

```
~/.modbot/
├── config.enc   # Token cifrado com PBKDF2 HMAC-SHA256 e cifra CTR (permissão 0600)
└── modbot.db    # Banco SQLite gerenciado pelo Tortoise-ORM (permissão 0700)
```

> [!IMPORTANT]
> **Compatibilidade Mobile / Termux**: O algoritmo de cifragem utiliza estritamente a biblioteca padrão do Python (`hashlib`, `hmac`, `secrets`, `uuid`). Não há compilação de binários em C/Rust (como OpenSSL ou Fernet), garantindo execução imediata e estável no Termux no Android.

---

## 📜 Comandos Disponíveis (Slash Commands)

Todos os comandos utilizam o sistema nativo de comandos de barra (`/`) do Discord com permissões integradas.

### ⚙️ Administração e Configuração
| Comando | Descrição | Permissão Recomendada |
| :--- | :--- | :--- |
| `/setup` | Define o **Cargo Master** (administração máxima do bot no servidor). | Administrador |
| `/sync` | Sincroniza os comandos de barra com o Discord (`escopo: servidor_atual` para testes imediatos). | Administrador ou Master |
| `/config_canal` | Configura canais para boas-vindas, saídas e logs do servidor. | Cargo Master |
| `/gerenciamento` | Exibe painel administrativo com estatísticas e métricas de execução do bot. | Cargo Master |

### 🛡️ Moderação e Proteção
| Comando | Descrição | Permissão Recomendada |
| :--- | :--- | :--- |
| `/protecao` | Ativa ou desativa a contenção conservadora anti-raid de novos bots. | Cargo Master |
| `/expulsar` | Expulsa um membro respeitando a hierarquia nativa de cargos do Discord. | Expulsar Membros |
| `/cargo` | Adiciona ou remove cargos de um membro com verificação de hierarquia. | Gerenciar Cargos |

### 🎫 Sistema de Tickets
| Comando | Descrição | Permissão Recomendada |
| :--- | :--- | :--- |
| `/config_tickets` | Define a categoria onde os tickets serão criados e o cargo de suporte. | Cargo Master |
| `/ticket_painel` | Publica o painel interativo de abertura de tickets no canal desejado. | Cargo Master |
| `/ticket_adicionar` | Concede acesso de um membro adicional a um ticket já em aberto. | Cargo Suporte / Master |

---

## 🏗️ Estrutura do Projeto

```
ModBot/
├── src/
│   └── modbot/
│       ├── __init__.py
│       ├── main.py             # CLI moderna construída com Typer
│       ├── bot.py              # Classe ModBot(commands.Bot) e ciclo de vida
│       ├── cogs/               # Módulos de comandos desacoplados
│       │   ├── management.py   # Métricas e status do bot
│       │   ├── moderation.py   # Expulsão, cargos e anti-raid
│       │   ├── setup.py        # Configuração inicial e cargo master
│       │   ├── staff.py        # Comandos de suporte e equipe
│       │   ├── sync.py         # Sincronização de slash commands
│       │   ├── tickets.py      # Sistema completo de atendimento com Views
│       │   ├── voice_logs.py   # Rastreamento de canais de voz
│       │   └── welcome.py      # Boas-vindas e logs de membros
│       ├── database/           # Configuração do Tortoise-ORM e models
│       │   ├── database.py     # Inicializador com persistência em ~/.modbot/
│       │   └── models.py       # Modelos de dados relacionais
│       └── utils/
│           ├── crypto.py       # Criptografia pura em Python (Termux/Cross-platform)
│           └── permissions.py  # Checagens de hierarquia e cargo master
├── pyproject.toml              # Metadados e dependências (Hatchling + UV)
└── README.md                   # Documentação do projeto
```

---

## 🔒 Segurança e Permissões

- **Hierarquia de Cargos**: O cargo do bot no Discord deve estar posicionado **acima** dos cargos que ele gerencia para poder atribuir ou revogar permissões.
- **Cargo Master**: Uma camada de autorização configurável do ModBot que complementa as permissões de Administrador nativas.
- **Anti-Raid Conservador**: Realiza checagem cruzada em logs de auditoria antes de conter bots suspeitos, evitando falsos positivos contra integrações legítimas.
- **Botões Persistentes**: As Views de tickets utilizam `custom_id` fixos, garantindo que botões continuem funcionando mesmo após reiniciar o bot.

---

<div align="center">

Desenvolvido com carinho para a comunidade Discord. 🚀  
Dúvidas ou sugestões? Abra uma [Issue](https://github.com/vinifreittas/ModBot/issues)!

</div>
