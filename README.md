# MeuBot Discord

Bot modular para Discord em Python, com discord.py 2.x e Tortoise ORM.

## Requisitos
- Python 3.10 ou superior
- Aplicação e bot criados no Discord Developer Portal
- Intents `Server Members Intent` e `Message Content Intent` habilitados no portal
- Permissões recomendadas: View Channels, Send Messages, Embed Links, Read Message History, Manage Channels, Kick Members e Manage Roles (somente se usar esses recursos)

## Instalação
1. Crie um ambiente virtual:
   - Windows: `py -m venv .venv` e `.venv\\Scripts\\activate`
   - Linux/macOS: `python3 -m venv .venv` e `source .venv/bin/activate`
2. Instale: `pip install -r requirements.txt`
3. Copie `.env.example` para `.env` e insira o token em `DISCORD_TOKEN`.
4. Convide o bot com os escopos `bot` e `applications.commands`.
5. Execute: `python main.py`

O banco SQLite `db.sqlite3` será criado automaticamente. Não compartilhe o token do bot.

## Comandos iniciais
- `/setup`: administrador escolhe o Cargo Master.
- `/config_canal`: configura boas-vindas, saídas e canais de logs.
- `/config_tickets`: configura a categoria e o cargo de suporte.
- `/ticket_painel`: publica o painel de abertura de tickets.
- `/gerenciamento`: métricas e acesso ao painel.
- `/cargo`: adiciona/remove um cargo, com verificação de hierarquia.
- `/expulsar`: expulsa um membro com permissão adequada.
- `/protecao`: liga/desliga a contenção conservadora de novos bots.
- `/ticket_adicionar`: concede acesso a um membro ao canal de ticket.

## Segurança e limitações
- O Cargo Master é uma autorização própria do bot; a hierarquia e permissões do Discord continuam valendo.
- O bot precisa ter permissões de canal e estar acima dos cargos que gerencia.
- O módulo Anti-Raid não remove cargos de pessoas automaticamente. Audit Logs podem estar indisponíveis ou atrasados, então nenhuma ação de punição contra o autor é feita com base apenas em uma suposição.
- A duração de call é aproximada e mantida em memória; reiniciar o bot perde as sessões em andamento.
- Este é um ponto de partida funcional, não um sistema anti-raid infalível. Teste em servidor privado antes de usar em produção.
