import asyncio
import json
import re
import urllib.request
import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import get_guild_config
from modbot.utils.permissions import require_master

# IDs configurados
CANAL_RESPOSTAS_ID = 1562821067506982932
CANAL_RESULTADOS_ID = 1562820824602378263
CARGO_EQUIPE_ID = 1562855905953976472

IMAGEM_APROVADO_URL = (
    "https://cdn.discordapp.com/attachments/1532208511545770107/1571657505124130927/aprovado.png"
)

# Se quiser que os canais #form-usuario sejam criados em uma categoria específica,
# coloque o ID dela abaixo. Se deixar None, cria na mesma categoria do painel.
CATEGORIA_FORMULARIOS_ID: int | None = None

PERGUNTAS = [
    "1️⃣ **Nome/Nick no Roblox:**",
    "2️⃣ **Idade:** *(Lembrando que buscamos maturidade para o cargo)*",
    "3️⃣ **Em quais horários você costuma ficar online?** *(Manhã, Tarde, Noite ou Madrugada)*",
    "4️⃣ **Já trabalhou em algum outro mapa ou evento (PDP, etc)?** Se sim, qual era seu cargo?",
    "5️⃣ **Por que você quer entrar para a Staff da Baile da Vila 🏡?**",
    "6️⃣ **O que diferencia você dos outros candidatos?**",
    "7️⃣ **Como você reage em situações de conflito ou desrespeito às regras?**",
    "8️⃣ **De 0 a 10, qual seu nível de conhecimento sobre comandos de administração (Admin Commands)?** Cite alguns.",
    "9️⃣ **Se um influenciador chegar no evento descumprindo as regras, qual seria sua postura?**",
    "🔟 **Você tem facilidade em gravar provas (vídeos/prints) caso precise banir alguém?**",
    "1️⃣1️⃣ **Termo de Ciência:** *Estou ciente de que o cargo exige responsabilidade e que abusos de poder resultarão em remoção imediata.* Responda com **Sim** para confirmar.",
    "1️⃣2️⃣ **Compromisso Visual:** *Comprometo-me a seguir a paleta de cores e o padrão visual da equipe durante os eventos.* Responda com **Sim** para confirmar.",
    "1️⃣3️⃣ **Número do WhatsApp:**",
]

# Evita que o mesmo usuário abra dois formulários ao mesmo tempo
formularios_ativos: set[int] = set()


def _verificar_roblox_sync(username: str) -> dict | None:
    """Consulta a API pública do Roblox para verificar se o nick existe."""
    try:
        payload = json.dumps(
            {"usernames": [username], "excludeBannedUsers": False}
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://users.roblox.com/v1/usernames/users",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            users = data.get("data", [])
            return users[0] if users else None
    except Exception:
        return None


async def verificar_conta_roblox(username: str) -> dict | None:
    return await asyncio.to_thread(_verificar_roblox_sync, username.strip())


class DecisaoCandidaturaView(discord.ui.View):
    def __init__(self, candidato_id: int | None = None) -> None:
        super().__init__(timeout=None)
        self.candidato_id = candidato_id

    def _extrair_candidato_id(self, interaction: discord.Interaction) -> int | None:
        if self.candidato_id is not None:
            return self.candidato_id
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            if embed.author and embed.author.name:
                match = re.search(r"\((\d{15,22})\)", embed.author.name)
                if match:
                    return int(match.group(1))
            for field in embed.fields:
                if field.name and "Usuário" in field.name and field.value:
                    match = re.search(r"\((\d{15,22})\)", field.value)
                    if match:
                        return int(match.group(1))
        return None

    def _extrair_nick_roblox(self, interaction: discord.Interaction) -> str:
        if interaction.message and interaction.message.embeds:
            for field in interaction.message.embeds[0].fields:
                if field.name and ("1️⃣" in field.name or "nick" in field.name.lower()):
                    return field.value or "Não informado"
        return "Não informado"

    @discord.ui.button(
        label="✅ Aprovar",
        style=discord.ButtonStyle.success,
        custom_id="candidatura_aprovar_baile_da_vila",
    )
    async def aprovar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return

        candidato_id = self._extrair_candidato_id(interaction)
        if not candidato_id:
            return await interaction.response.send_message(
                "❌ Não foi possível identificar o candidato.", ephemeral=True
            )

        nick_roblox = self._extrair_nick_roblox(interaction)

        membro = interaction.guild.get_member(candidato_id)
        if membro is None:
            try:
                membro = await interaction.guild.fetch_member(candidato_id)
            except discord.NotFound:
                return await interaction.response.send_message(
                    "❌ O membro não está mais no servidor.", ephemeral=True
                )

        cargo = interaction.guild.get_role(CARGO_EQUIPE_ID)
        if cargo is None:
            return await interaction.response.send_message(
                "❌ Cargo da equipe não encontrado. Verifique o ID do cargo.",
                ephemeral=True,
            )

        try:
            await membro.add_roles(
                cargo, reason=f"Aprovado na candidatura por {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Não tenho permissão para adicionar esse cargo. Verifique a hierarquia do bot.",
                ephemeral=True,
            )

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        # Atualiza a ficha da candidatura
        if interaction.message and interaction.message.embeds:
            embed_atualizado = interaction.message.embeds[0].copy()
            embed_atualizado.color = 3066993
            embed_atualizado.add_field(
                name="🔍 Avaliador",
                value=interaction.user.mention,
                inline=True,
            )
            embed_atualizado.set_footer(
                text=f"✅ APROVADO por {interaction.user.display_name} | ID: {membro.id}"
            )
            await interaction.message.edit(embed=embed_atualizado, view=self)
        else:
            await interaction.message.edit(view=self)

        # Publica no canal de aprovados
        canal_resultados = interaction.guild.get_channel(CANAL_RESULTADOS_ID)
        if isinstance(canal_resultados, discord.TextChannel):
            embed_aprovado = discord.Embed(
                title="🎉 Novo Staff Aprovado!",
                description=f"{membro.mention} foi **aprovado(a)** na candidatura de Staff!",
                color=3066993,
                timestamp=discord.utils.utcnow(),
            )
            avatar_url = membro.display_avatar.url if membro.display_avatar else None
            embed_aprovado.set_author(
                name=membro.display_name,
                icon_url=avatar_url,
            )
            if avatar_url:
                embed_aprovado.set_thumbnail(url=avatar_url)

            embed_aprovado.add_field(
                name="👤 Usuário",
                value=f"{membro.mention}\n({membro.id})",
                inline=True,
            )
            embed_aprovado.add_field(
                name="🎮 Nick Roblox",
                value=nick_roblox,
                inline=True,
            )
            embed_aprovado.add_field(
                name="✅ Aprovado por",
                value=interaction.user.mention,
                inline=True,
            )

            if IMAGEM_APROVADO_URL:
                embed_aprovado.set_image(url=IMAGEM_APROVADO_URL)

            embed_aprovado.set_footer(
                text="Baile da Vila 🏡 • Sistema de Candidatura",
            )

            try:
                await canal_resultados.send(
                    content=membro.mention, embed=embed_aprovado
                )
            except discord.HTTPException:
                embed_aprovado.set_image(url=None)
                await canal_resultados.send(
                    content=membro.mention, embed=embed_aprovado
                )

        # Envia mensagem no PV do membro aprovado
        try:
            await membro.send(
                f"🎉 Parabéns! Sua candidatura para Staff na **Baile da Vila 🏡** foi **aprovada** no servidor **{interaction.guild.name}**!"
            )
            pv_status = "PV enviado com sucesso."
        except discord.Forbidden:
            pv_status = "Não foi possível enviar PV (DM fechada)."

        await interaction.response.send_message(
            f"✅ {membro.mention} foi aprovado e o resultado foi publicado! ({pv_status})",
            ephemeral=True,
        )

    @discord.ui.button(
        label="❌ Reprovar",
        style=discord.ButtonStyle.danger,
        custom_id="candidatura_reprovar_baile_da_vila",
    )
    async def reprovar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return

        candidato_id = self._extrair_candidato_id(interaction)
        membro = interaction.guild.get_member(candidato_id) if candidato_id else None

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if interaction.message and interaction.message.embeds:
            embed_atualizado = interaction.message.embeds[0].copy()
            embed_atualizado.color = discord.Color.red()
            embed_atualizado.add_field(
                name="🔍 Avaliador",
                value=interaction.user.mention,
                inline=True,
            )
            embed_atualizado.set_footer(
                text=f"❌ REPROVADO por {interaction.user.display_name} | ID: {candidato_id or 'N/A'}"
            )
            await interaction.message.edit(embed=embed_atualizado, view=self)
        else:
            await interaction.message.edit(view=self)

        if membro:
            try:
                await membro.send(
                    f"📋 Olá {membro.mention}, agradecemos sua participação no processo seletivo da **Baile da Vila 🏡**. Desta vez sua candidatura não foi aprovada, mas você poderá tentar novamente em uma próxima oportunidade!"
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            "❌ Candidatura marcada como reprovada.", ephemeral=True
        )


async def iniciar_entrevista_ticket(
    bot: commands.Bot,
    canal: discord.TextChannel,
    candidato: discord.Member,
) -> None:
    total = len(PERGUNTAS)
    respostas: list[tuple[str, str]] = []

    def check(msg: discord.Message) -> bool:
        return (
            msg.author.id == candidato.id
            and msg.channel.id == canal.id
            and not msg.author.bot
        )

    try:
        await canal.send(
            f"👋 Olá {candidato.mention}! Bem-vindo ao seu formulário de candidatura para Staff da **Baile da Vila 🏡**.\n"
            f"Responda cada pergunta abaixo enviando uma mensagem neste canal. *(Digite `cancelar` a qualquer momento para encerrar)*."
        )

        for indice, pergunta in enumerate(PERGUNTAS, start=1):
            embed_pergunta = discord.Embed(
                title=f"Pergunta {indice} de {total}",
                description=pergunta,
                color=0xE74C3C,
            )
            await canal.send(embed=embed_pergunta)

            try:
                msg = await bot.wait_for("message", timeout=600.0, check=check)
            except asyncio.TimeoutError:
                await canal.send(
                    "⏰ Tempo esgotado (10 minutos sem resposta). Este canal será excluído em 10 segundos."
                )
                await asyncio.sleep(10)
                await canal.delete(reason="Tempo limite da candidatura expirado")
                return

            if msg.content.strip().lower() == "cancelar":
                await canal.send(
                    "❌ Candidatura cancelada. Este canal será excluído em 5 segundos."
                )
                await asyncio.sleep(5)
                await canal.delete(reason="Candidatura cancelada pelo usuário")
                return

            resposta_texto = msg.content.strip() or "[Anexo/Sem texto]"
            respostas.append((pergunta, resposta_texto))

        # Envia a ficha completa para o canal da Staff mencionando o cargo da equipe
        canal_respostas = candidato.guild.get_channel(CANAL_RESPOSTAS_ID)
        if isinstance(canal_respostas, discord.TextChannel):
            nick_roblox = respostas[0][1] if respostas else "Não informado"
            conta_roblox = await verificar_conta_roblox(nick_roblox)

            embed_ficha = discord.Embed(
                title="📋 Nova Candidatura de Staff",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow(),
            )
            avatar_url = (
                candidato.display_avatar.url if candidato.display_avatar else None
            )
            embed_ficha.set_author(
                name=f"{candidato.display_name} ({candidato.id})",
                icon_url=avatar_url,
            )

            embed_ficha.add_field(
                name="👤 Usuário",
                value=f"{candidato.mention}\n({candidato.id})",
                inline=False,
            )

            if conta_roblox:
                embed_ficha.add_field(
                    name="✅ Conta Roblox Verificada",
                    value=f"**{conta_roblox.get('name')}** (`ID: {conta_roblox.get('id')}`)",
                    inline=False,
                )
            else:
                embed_ficha.add_field(
                    name="⚠️ Conta Roblox não encontrada",
                    value=f"Não foi possível verificar a conta **{nick_roblox}** na API do Roblox. Verifique manualmente.",
                    inline=False,
                )

            for perg, resp in respostas:
                nome_limpo = perg.replace("**", "").replace("*", "")[:256]
                embed_ficha.add_field(
                    name=nome_limpo,
                    value=resp[:1024],
                    inline=False,
                )

            cargo_equipe = candidato.guild.get_role(CARGO_EQUIPE_ID)
            mencao_equipe = (
                cargo_equipe.mention if cargo_equipe else f"<@&{CARGO_EQUIPE_ID}>"
            )

            view_decisao = DecisaoCandidaturaView(candidato_id=candidato.id)
            await canal_respostas.send(
                content=mencao_equipe,
                embed=embed_ficha,
                view=view_decisao,
            )

        await canal.send(
            "✅ **Formulário concluído!** Suas respostas foram enviadas para a equipe da **Baile da Vila 🏡**.\n"
            "Este canal será fechado automaticamente em 10 segundos."
        )
        await asyncio.sleep(10)
        await canal.delete(reason="Formulário de candidatura concluído")
    finally:
        formularios_ativos.discard(candidato.id)


class BotaoCandidatar(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="📋 Quero me candidatar!",
            style=discord.ButtonStyle.danger,
            custom_id="candidatura_staff_baile_da_vila",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )

        if interaction.user.id in formularios_ativos:
            return await interaction.response.send_message(
                "⚠️ Você já possui um formulário de candidatura em andamento!",
                ephemeral=True,
            )

        nome_limpo = re.sub(r"[^a-z0-9]", "", interaction.user.name.lower()) or str(
            interaction.user.id
        )
        nome_canal = f"form-{nome_limpo}"[:95]

        canal_existente = discord.utils.get(
            interaction.guild.text_channels, name=nome_canal
        )
        if canal_existente:
            return await interaction.response.send_message(
                f"⚠️ Você já tem um canal de formulário aberto: {canal_existente.mention}",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        categoria = None
        if CATEGORIA_FORMULARIOS_ID:
            cat = interaction.guild.get_channel(CATEGORIA_FORMULARIOS_ID)
            if isinstance(cat, discord.CategoryChannel):
                categoria = cat
        elif isinstance(interaction.channel, discord.TextChannel):
            categoria = interaction.channel.category

        overwrites: dict[
            discord.Role | discord.Member, discord.PermissionOverwrite
        ] = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }

        try:
            canal_ticket = await interaction.guild.create_text_channel(
                name=nome_canal,
                category=categoria,
                overwrites=overwrites,
                reason=f"Formulário de Staff iniciado por {interaction.user}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ Não tenho permissão para criar canais neste servidor (`Gerenciar Canais`).",
                ephemeral=True,
            )

        formularios_ativos.add(interaction.user.id)
        await interaction.followup.send(
            f"✅ Seu formulário foi criado! Acesse {canal_ticket.mention} para responder às perguntas.",
            ephemeral=True,
        )

        bot: commands.Bot = interaction.client  # type: ignore[assignment]
        bot.loop.create_task(
            iniciar_entrevista_ticket(bot, canal_ticket, interaction.user)
        )


class PainelStaffLayout(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        conteudo = (
            "# 🏡 Candidatura para Staff — Baile da Vila 🏡\n\n"
            "-# Você quer fazer parte da equipe que organiza e garante a melhor experiência na **Baile da Vila 🏡**?\n\n"
            "-# **O que buscamos:**\n"
            "-# 🎯 Maturidade e responsabilidade\n"
            "-# 🛡️ Conhecimento de comandos de administração\n"
            "-# 🎥 Facilidade em registrar provas (prints/vídeos)\n"
            "-# 🤝 Boa comunicação e postura profissional\n\n"
            "-# **Como se candidatar:**\n"
            "-# Clique no botão abaixo e responda o formulário. Um canal exclusivo será criado para você!\n\n"
            "-# ⚠️ Todas as perguntas são obrigatórias. Abusos de poder resultarão em remoção imediata.\n\n"
            "-# Baile da Vila 🏡 • Processo Seletivo de Staff"
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay(conteudo),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(BotaoCandidatar()),
            accent_color=0xF1C40F,
        )
        self.add_item(container)


class Staff(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="cargo", description="Adiciona ou remove um cargo de um membro."
    )
    @app_commands.describe(
        membro="Membro alvo",
        cargo="Cargo a alterar",
        acao="Adicionar ou remover",
        motivo="Motivo opcional",
    )
    @app_commands.choices(
        acao=[
            app_commands.Choice(name="Promover (adicionar cargo)", value="add"),
            app_commands.Choice(name="Rebaixar (remover cargo)", value="remove"),
        ]
    )
    async def cargo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        cargo: discord.Role,
        acao: app_commands.Choice[str],
        motivo: str = "Não informado",
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return
        me = interaction.guild.me
        if (
            cargo.is_default()
            or cargo.managed
            or cargo >= me.top_role
            or membro.top_role >= me.top_role
        ):
            return await interaction.response.send_message(
                "A hierarquia do bot não permite alterar esse cargo/membro.",
                ephemeral=True,
            )
        try:
            if acao.value == "add":
                await membro.add_roles(
                    cargo, reason=f"{interaction.user}: {motivo[:300]}"
                )
                verb = "adicionado a"
            else:
                await membro.remove_roles(
                    cargo, reason=f"{interaction.user}: {motivo[:300]}"
                )
                verb = "removido de"
            await interaction.response.send_message(
                f"Cargo {cargo.mention} {verb} {membro.mention}. Motivo: {motivo[:300]}"
            )
            config = await get_guild_config(interaction.guild.id)
            log = (
                interaction.guild.get_channel(config.staff_log_channel_id)
                if config.staff_log_channel_id
                else None
            )
            if isinstance(log, discord.TextChannel):
                log_message = (
                    "🎖️ **Cargo alterado**\n"
                    f"Responsável: {interaction.user.mention}\n"
                    f"Membro: {membro.mention}\n"
                    f"Cargo: {cargo.mention}\n"
                    f"Ação: {acao.name}\n"
                    f"Motivo: {motivo[:300]}"
                )
                await log.send(log_message)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para alterar esse cargo.", ephemeral=True
            )

    @app_commands.command(
        name="painel_staff",
        description="Envia o painel de candidatura para Staff no canal atual",
    )
    async def painel_staff(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Use em um servidor.", ephemeral=True
            )
        if not await require_master(interaction):
            return

        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "Não foi possível enviar o painel neste canal.", ephemeral=True
            )

        try:
            await channel.send(view=PainelStaffLayout())
            await interaction.response.send_message(
                "✅ Painel de candidatura enviado com sucesso neste canal!",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para enviar mensagens neste canal.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Staff(bot))
    bot.add_view(PainelStaffLayout())
    bot.add_view(DecisaoCandidaturaView())