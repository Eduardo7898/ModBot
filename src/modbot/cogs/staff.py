import asyncio
import json
import re
import urllib.request
import discord
from discord import app_commands
from discord.ext import commands

from modbot.database.models import get_guild_config
from modbot.utils.permissions import require_master

CANAL_RESPOSTAS_ID = 1562821067506982932
CANAL_RESULTADOS_ID = 1562820824602378263
CARGO_EQUIPE_ID = 1562855905953976472
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

formularios_ativos: set[int] = set()


def _bloco(texto: str, limite: int = 1024) -> str:
    limpo = texto.replace("```", "`\u200b``").strip() or "[Anexo/Sem texto]"
    return f"```\n{limpo[:max(1, limite - 8)]}\n```"


def _roblox_sync(username: str) -> dict | None:
    try:
        payload = json.dumps({"usernames": [username], "excludeBannedUsers": False}).encode()
        req = urllib.request.Request(
            "[https://users.roblox.com/v1/usernames/users](https://users.roblox.com/v1/usernames/users)",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            users = json.loads(resp.read().decode()).get("data", [])
            return users[0] if users else None
    except Exception:
        return None


async def _extrair_membro_e_cargo(
    interaction: discord.Interaction, candidato_id: int | None
) -> tuple[discord.Member | None, discord.Role | None]:
    if not interaction.guild or not candidato_id:
        return None, None
    membro = interaction.guild.get_member(candidato_id)
    if membro is None:
        try:
            membro = await interaction.guild.fetch_member(candidato_id)
        except discord.NotFound:
            membro = None
    return membro, interaction.guild.get_role(CARGO_EQUIPE_ID)


class DecisaoCandidaturaView(discord.ui.View):
    def __init__(self, candidato_id: int | None = None) -> None:
        super().__init__(timeout=None)
        self.candidato_id = candidato_id

    def _candidato_id(self, interaction: discord.Interaction) -> int | None:
        if self.candidato_id is not None:
            return self.candidato_id
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            textos = [embed.author.name if embed.author else ""] + [
                f.value or "" for f in embed.fields if f.name and "Usuário" in f.name
            ]
            for txt in textos:
                if m := re.search(r"\((\d{15,22})\)", txt):
                    return int(m.group(1))
        return None

    def _nick_roblox(self, interaction: discord.Interaction) -> str:
        if interaction.message and interaction.message.embeds:
            for f in interaction.message.embeds[0].fields:
                if f.name and ("1️⃣" in f.name or "nick" in f.name.lower()):
                    val = (f.value or "Não informado").strip()
                    if val.startswith("```") and val.endswith("```") and len(val.splitlines()) >= 3:
                        return "\n".join(val.splitlines()[1:-1]).strip() or "Não informado"
                    return val
        return "Não informado"

    async def _finalizar_ficha(
        self, interaction: discord.Interaction, aprovado: bool, membro_id: int | None
    ) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0].copy()
            emb.color = 3066993 if aprovado else discord.Color.red()
            emb.add_field(name="🔍 Avaliador", value=interaction.user.mention, inline=True)
            tag = "APROVADO" if aprovado else "REPROVADO"
            emb.set_footer(text=f"{'✅' if aprovado else '❌'} {tag} por {interaction.user.display_name} | ID: {membro_id or 'N/A'}")
            await interaction.message.edit(embed=emb, view=self)
        elif interaction.message:
            await interaction.message.edit(view=self)

    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success, custom_id="candidatura_aprovar_baile_da_vila")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return

        candidato_id = self._candidato_id(interaction)
        membro, cargo = await _extrair_membro_e_cargo(interaction, candidato_id)
        if not membro:
            return await interaction.response.send_message("❌ Candidato não encontrado no servidor.", ephemeral=True)
        if not cargo:
            return await interaction.response.send_message("❌ Cargo da equipe não encontrado.", ephemeral=True)

        try:
            await membro.add_roles(cargo, reason=f"Aprovado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Sem permissão para adicionar o cargo.", ephemeral=True)

        await self._finalizar_ficha(interaction, True, membro.id)

        canal_res = interaction.guild.get_channel(CANAL_RESULTADOS_ID)
        if isinstance(canal_res, discord.TextChannel):
            avatar = membro.display_avatar.url if membro.display_avatar else None
            emb = discord.Embed(
                title="🎉 Novo Staff Aprovado!",
                description=f"{membro.mention} foi **aprovado(a)** na candidatura de Staff!",
                color=3066993,
                timestamp=discord.utils.utcnow(),
            )
            emb.set_author(name=membro.display_name, icon_url=avatar)
            if avatar:
                emb.set_thumbnail(url=avatar)
            emb.add_field(name="👤 Usuário", value=f"{membro.mention}\n({membro.id})", inline=True)
            emb.add_field(name="🎮 Nick Roblox", value=self._nick_roblox(interaction), inline=True)
            emb.add_field(name="✅ Aprovado por", value=interaction.user.mention, inline=True)
            emb.set_footer(text="Baile da Vila 🏡 • Sistema de Candidatura")
            await canal_res.send(content=membro.mention, embed=emb)

        try:
            await membro.send(
                f"🎉 Parabéns! Sua candidatura para Staff na **Baile da Vila 🏡** foi **aprovada** no servidor **{interaction.guild.name}**!"
            )
            pv = "PV enviado com sucesso."
        except discord.Forbidden:
            pv = "Não foi possível enviar PV (DM fechada)."

        await interaction.response.send_message(f"✅ {membro.mention} aprovado! ({pv})", ephemeral=True)

    @discord.ui.button(label="❌ Reprovar", style=discord.ButtonStyle.danger, custom_id="candidatura_reprovar_baile_da_vila")
    async def reprovar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return

        candidato_id = self._candidato_id(interaction)
        membro = interaction.guild.get_member(candidato_id) if candidato_id else None
        await self._finalizar_ficha(interaction, False, candidato_id)

        if membro:
            try:
                await membro.send(
                    f"📋 Olá {membro.mention}, agradecemos sua participação no processo seletivo da **Baile da Vila 🏡**. Desta vez sua candidatura não foi aprovada, mas você poderá tentar novamente em uma próxima oportunidade!"
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message("❌ Candidatura marcada como reprovada.", ephemeral=True)


async def _excluir_canal(canal: discord.TextChannel, motivo: str) -> None:
    try:
        await canal.delete(reason=motivo)
    except (discord.Forbidden, discord.NotFound):
        pass


async def iniciar_entrevista_ticket(bot: commands.Bot, canal: discord.TextChannel, candidato: discord.Member) -> None:
    respostas: list[tuple[str, str]] = []
    check = lambda m: m.author.id == candidato.id and m.channel.id == canal.id and not m.author.bot

    try:
        await canal.send(
            f"👋 Olá {candidato.mention}! Bem-vindo ao seu formulário de candidatura para Staff da **Baile da Vila 🏡**.\n"
            f"Responda cada pergunta abaixo enviando uma mensagem neste canal. *(Digite `cancelar` a qualquer momento para encerrar)*."
        )

        for idx, pergunta in enumerate(PERGUNTAS, start=1):
            await canal.send(embed=discord.Embed(title=f"Pergunta {idx} de {len(PERGUNTAS)}", description=pergunta, color=0xE74C3C))
            try:
                msg = await bot.wait_for("message", timeout=600.0, check=check)
            except asyncio.TimeoutError:
                await canal.send("⏰ Tempo esgotado (10 minutos sem resposta). Este canal será excluído em 10 segundos.")
                await asyncio.sleep(10)
                await _excluir_canal(canal, "Tempo limite da candidatura expirado")
                return

            if msg.content.strip().lower() == "cancelar":
                await canal.send("❌ Candidatura cancelada. Este canal será excluído em 5 segundos.")
                await asyncio.sleep(5)
                await _excluir_canal(canal, "Candidatura cancelada pelo usuário")
                return

            respostas.append((pergunta, msg.content.strip() or "[Anexo/Sem texto]"))

        canal_res = candidato.guild.get_channel(CANAL_RESPOSTAS_ID)
        if isinstance(canal_res, discord.TextChannel):
            nick = respostas[0][1] if respostas else "Não informado"
            conta = await asyncio.to_thread(_roblox_sync, nick.strip())
            avatar = candidato.display_avatar.url if candidato.display_avatar else None

            ficha = discord.Embed(title="📋 Nova Candidatura de Staff", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
            ficha.set_author(name=f"{candidato.display_name} ({candidato.id})", icon_url=avatar)
            ficha.add_field(name="👤 Usuário", value=f"{candidato.mention}\n({candidato.id})", inline=False)
            if conta:
                ficha.add_field(name="✅ Conta Roblox Verificada", value=_bloco(f"{conta.get('name')} (ID: {conta.get('id')})"), inline=False)
            else:
                ficha.add_field(name="⚠️ Conta Roblox não encontrada", value=f"Não foi possível verificar a conta **{nick}** na API do Roblox. Verifique manualmente.", inline=False)

            for perg, resp in respostas:
                ficha.add_field(name=perg.replace("**", "").replace("*", "")[:256], value=_bloco(resp), inline=False)

            cargo_eq = candidato.guild.get_role(CARGO_EQUIPE_ID)
            mencao = cargo_eq.mention if cargo_eq else f"<@&{CARGO_EQUIPE_ID}>"
            await canal_res.send(content=mencao, embed=ficha, view=DecisaoCandidaturaView(candidato_id=candidato.id))

        await canal.send("✅ **Formulário concluído!** Suas respostas foram enviadas para a equipe da **Baile da Vila 🏡**.\nEste canal será fechado automaticamente em 10 segundos.")
        await asyncio.sleep(10)
        await _excluir_canal(canal, "Formulário de candidatura concluído")
    finally:
        formularios_ativos.discard(candidato.id)


class BotaoCandidatar(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="📋 Quero me candidatar!", style=discord.ButtonStyle.danger, custom_id="candidatura_staff_baile_da_vila")

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if interaction.user.id in formularios_ativos:
            return await interaction.response.send_message("⚠️ Você já possui um formulário de candidatura em andamento!", ephemeral=True)

        slug = re.sub(r"[^a-z0-9]", "", interaction.user.name.lower()) or str(interaction.user.id)
        nome_canal = f"form-{slug}"[:95]
        if existente := discord.utils.get(interaction.guild.text_channels, name=nome_canal):
            return await interaction.response.send_message(f"⚠️ Você já tem um canal de formulário aberto: {existente.mention}", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        cat_id = CATEGORIA_FORMULARIOS_ID
        categoria = interaction.guild.get_channel(cat_id) if cat_id else getattr(interaction.channel, "category", None)
        if not isinstance(categoria, discord.CategoryChannel):
            categoria = None

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        try:
            ticket = await interaction.guild.create_text_channel(name=nome_canal, category=categoria, overwrites=overwrites, reason=f"Formulário de Staff por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send("❌ Não tenho permissão para criar canais (`Gerenciar Canais`).", ephemeral=True)

        formularios_ativos.add(interaction.user.id)
        await interaction.followup.send(f"✅ Seu formulário foi criado! Acesse {ticket.mention} para responder às perguntas.", ephemeral=True)
        bot: commands.Bot = interaction.client  # type: ignore[assignment]
        bot.loop.create_task(iniciar_entrevista_ticket(bot, ticket, interaction.user))


class PainelStaffLayout(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        texto = (
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
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(texto),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                discord.ui.ActionRow(BotaoCandidatar()),
                accent_color=0xF1C40F,
            )
        )


class Staff(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="cargo", description="Adiciona ou remove um cargo de um membro.")
    @app_commands.describe(membro="Membro alvo", cargo="Cargo a alterar", acao="Adicionar ou remover", motivo="Motivo opcional")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Promover (adicionar cargo)", value="add"),
        app_commands.Choice(name="Rebaixar (remover cargo)", value="remove"),
    ])
    async def cargo(self, interaction: discord.Interaction, membro: discord.Member, cargo: discord.Role, acao: app_commands.Choice[str], motivo: str = "Não informado") -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return
        me = interaction.guild.me
        if cargo.is_default() or cargo.managed or cargo >= me.top_role or membro.top_role >= me.top_role:
            return await interaction.response.send_message("A hierarquia do bot não permite alterar esse cargo/membro.", ephemeral=True)
        try:
            if acao.value == "add":
                await membro.add_roles(cargo, reason=f"{interaction.user}: {motivo[:300]}")
                verb = "adicionado a"
            else:
                await membro.remove_roles(cargo, reason=f"{interaction.user}: {motivo[:300]}")
                verb = "removido de"
            await interaction.response.send_message(f"Cargo {cargo.mention} {verb} {membro.mention}. Motivo: {motivo[:300]}")
            config = await get_guild_config(interaction.guild.id)
            log = interaction.guild.get_channel(config.staff_log_channel_id) if config.staff_log_channel_id else None
            if isinstance(log, discord.TextChannel):
                await log.send(f"🎖️ **Cargo alterado**\nResponsável: {interaction.user.mention}\nMembro: {membro.mention}\nCargo: {cargo.mention}\nAção: {acao.name}\nMotivo: {motivo[:300]}")
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão para alterar esse cargo.", ephemeral=True)

    @app_commands.command(name="painel_staff", description="Envia o painel de candidatura para Staff no canal atual")
    async def painel_staff(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("Não foi possível enviar o painel neste canal.", ephemeral=True)
        try:
            await interaction.channel.send(view=PainelStaffLayout())
            await interaction.response.send_message("✅ Painel de candidatura enviado com sucesso neste canal!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão para enviar mensagens neste canal.", ephemeral=True)

    @app_commands.command(name="reset_form_staff", description="Reseta todas as candidaturas (libera geral)")
    async def reset_form_staff(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not await require_master(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        ativos = len(formularios_ativos)
        formularios_ativos.clear()
        removidos = 0
        for canal in list(interaction.guild.text_channels):
            if canal.name.startswith("form-"):
                try:
                    await canal.delete(reason=f"Reset geral de candidaturas por {interaction.user}")
                    removidos += 1
                except (discord.Forbidden, discord.NotFound):
                    pass
        await interaction.followup.send(f"✅ Todas as candidaturas foram resetadas! ({ativos} bloqueio(s) limpo(s) e {removidos} canal(is) `#form-*` removido(s). Geral liberado!)", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Staff(bot))
    bot.add_view(PainelStaffLayout())
    bot.add_view(DecisaoCandidaturaView())