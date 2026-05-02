print("🔄 Iniciando o bot...")
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime

# ============================================================
# CONFIGURAÇÕES DO BOT
# ============================================================
TOKEN = os.getenv("TOKEN")         # Cole o token do seu bot aqui
GUILD_ID = 1473091926432546959              # ID do seu servidor Discord
CATEGORIA_TICKETS = "Tickets"     # Nome da categoria onde os tickets serão criados
CARGO_SUPORTE = "Suporte"         # Nome do cargo da equipe de suporte
CANAL_LOGS = "logs-tickets"       # Nome do canal de logs

# ============================================================
# CONFIGURAÇÃO DO BOT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ============================================================
# BANCO DE DADOS SIMPLES (arquivo JSON)
# ============================================================
DB_FILE = "tickets.json"

def carregar_tickets():
    """Carrega os tickets salvos no arquivo JSON."""
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_tickets(dados):
    """Salva os tickets no arquivo JSON."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def proximo_id():
    """Gera o próximo ID de ticket."""
    tickets = carregar_tickets()
    if not tickets:
        return 1
    return max(int(k) for k in tickets.keys()) + 1


# ============================================================
# VIEWS (Botões interativos)
# ============================================================

class BotaoAbrirTicket(discord.ui.View):
    """
    View com o botão 'Abrir Ticket'.
    Fica no canal de suporte para os usuários clicarem.
    """
    def __init__(self):
        super().__init__(timeout=None)  # Sem timeout - botão permanente

    @discord.ui.button(
        label="🎫 Abrir Ticket",
        style=discord.ButtonStyle.green,
        custom_id="abrir_ticket"
    )
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalTicket())


class BotaoControleTicket(discord.ui.View):
    """
    Botões de controle dentro do ticket:
    - Fechar ticket
    - Assumir atendimento
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Assumir",
        style=discord.ButtonStyle.blurple,
        custom_id="assumir_ticket"
    )
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cargo_suporte = discord.utils.get(guild.roles, name=CARGO_SUPORTE)

        # Verifica se quem clicou tem o cargo de suporte
        if cargo_suporte not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ Apenas a equipe de suporte pode assumir tickets!",
                ephemeral=True  # Só o usuário vê essa mensagem
            )
            return

        # Atualiza o ticket no banco de dados
        tickets = carregar_tickets()
        canal_id = str(interaction.channel.id)

        for ticket_id, ticket in tickets.items():
            if ticket["canal_id"] == canal_id:
                ticket["atendente"] = interaction.user.name
                ticket["status"] = "em_atendimento"
                salvar_tickets(tickets)

                embed = discord.Embed(
                    title="✅ Ticket Assumido",
                    description=f"{interaction.user.mention} está atendendo este ticket!",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.response.send_message(embed=embed)

                # Renomeia o canal
                await interaction.channel.edit(
                    name=f"em-atendimento-{interaction.channel.name.split('-')[-1]}"
                )
                return

        await interaction.response.send_message("Ticket não encontrado.", ephemeral=True)

    @discord.ui.button(
        label="🔒 Fechar Ticket",
        style=discord.ButtonStyle.red,
        custom_id="fechar_ticket"
    )
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cargo_suporte = discord.utils.get(guild.roles, name=CARGO_SUPORTE)

        # Suporte OU o próprio usuário pode fechar
        tickets = carregar_tickets()
        canal_id = str(interaction.channel.id)
        ticket_dono = None

        for ticket_id, ticket in tickets.items():
            if ticket["canal_id"] == canal_id:
                ticket_dono = ticket["usuario_id"]
                break

        pode_fechar = (
            cargo_suporte in interaction.user.roles or
            str(interaction.user.id) == ticket_dono
        )

        if not pode_fechar:
            await interaction.response.send_message(
                "❌ Você não tem permissão para fechar este ticket.",
                ephemeral=True
            )
            return

        # Mostra confirmação antes de fechar
        await interaction.response.send_message(
            "Tem certeza que deseja fechar o ticket?",
            view=BotaoConfirmarFechamento(),
            ephemeral=True
        )


class BotaoConfirmarFechamento(discord.ui.View):
    """Confirmação de fechamento do ticket."""

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.red)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await fechar_ticket(interaction)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.grey)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fechamento cancelado.", ephemeral=True)


# ============================================================
# MODAL (Formulário de abertura de ticket)
# ============================================================

class ModalTicket(discord.ui.Modal, title="Abrir Ticket de Suporte"):
    """
    Formulário que aparece quando o usuário clica em 'Abrir Ticket'.
    """

    assunto = discord.ui.TextInput(
        label="Assunto",
        placeholder="Ex: Problema com meu pedido #1234",
        max_length=100,
        required=True
    )

    descricao = discord.ui.TextInput(
        label="Descreva seu problema",
        style=discord.TextStyle.paragraph,
        placeholder="Explique com detalhes o que está acontecendo...",
        max_length=500,
        required=True
    )

    prioridade = discord.ui.TextInput(
        label="Prioridade (baixa / média / alta)",
        placeholder="baixa",
        max_length=10,
        required=False,
        default="baixa"
    )

    async def on_submit(self, interaction: discord.Interaction):
        await criar_ticket(interaction, self.assunto.value, self.descricao.value, self.prioridade.value)


# ============================================================
# FUNÇÕES PRINCIPAIS
# ============================================================

async def criar_ticket(interaction: discord.Interaction, assunto: str, descricao: str, prioridade: str):
    """Cria um novo canal de ticket para o usuário."""
    guild = interaction.guild
    usuario = interaction.user

    # Busca ou cria a categoria de tickets
    categoria = discord.utils.get(guild.categories, name=CATEGORIA_TICKETS)
    if not categoria:
        categoria = await guild.create_category(CATEGORIA_TICKETS)

    # Busca o cargo de suporte
    cargo_suporte = discord.utils.get(guild.roles, name=CARGO_SUPORTE)

    # Define o ID do ticket
    ticket_id = proximo_id()

    # Permissões do canal
    # - @everyone: não vê o canal
    # - Usuário: pode ver e enviar mensagens
    # - Suporte: pode ver e gerenciar
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        usuario: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }

    if cargo_suporte:
        overwrites[cargo_suporte] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_messages=True
        )

    # Cria o canal com nome: ticket-0001
    nome_canal = f"ticket-{ticket_id:04d}"
    canal = await guild.create_text_channel(
        name=nome_canal,
        category=categoria,
        overwrites=overwrites,
        topic=f"Ticket de {usuario.name} | {assunto}"
    )

    # Salva no banco de dados
    tickets = carregar_tickets()
    tickets[str(ticket_id)] = {
        "id": ticket_id,
        "canal_id": str(canal.id),
        "usuario_id": str(usuario.id),
        "usuario_nome": usuario.name,
        "assunto": assunto,
        "descricao": descricao,
        "prioridade": prioridade.lower(),
        "status": "aberto",
        "atendente": None,
        "aberto_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fechado_em": None
    }
    salvar_tickets(tickets)

    # Define cor baseada na prioridade
    cores = {"alta": discord.Color.red(), "média": discord.Color.yellow(), "baixa": discord.Color.green()}
    cor = cores.get(prioridade.lower(), discord.Color.blurple())

    # Embed principal do ticket
    embed = discord.Embed(
        title=f"🎫 Ticket #{ticket_id:04d}",
        color=cor,
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Usuário", value=usuario.mention, inline=True)
    embed.add_field(name="⚡ Prioridade", value=prioridade.capitalize(), inline=True)
    embed.add_field(name="📋 Status", value="🟢 Aberto", inline=True)
    embed.add_field(name="📌 Assunto", value=assunto, inline=False)
    embed.add_field(name="📝 Descrição", value=descricao, inline=False)
    embed.set_footer(text="Use os botões abaixo para gerenciar o ticket")

    mencao = cargo_suporte.mention if cargo_suporte else "@Suporte"
    await canal.send(
        content=f"{usuario.mention} | {mencao}",
        embed=embed,
        view=BotaoControleTicket()
    )

    # Notifica o usuário (mensagem efêmera)
    await interaction.response.send_message(
        f"✅ Seu ticket foi criado! Acesse {canal.mention}",
        ephemeral=True
    )

    # Envia log
    await enviar_log(guild, "aberto", ticket_id, usuario, assunto, None)


async def fechar_ticket(interaction: discord.Interaction):
    """Fecha o ticket, salva log e deleta o canal."""
    guild = interaction.guild
    canal = interaction.channel
    canal_id = str(canal.id)

    tickets = carregar_tickets()
    ticket_encontrado = None
    ticket_id_key = None

    for tid, ticket in tickets.items():
        if ticket["canal_id"] == canal_id:
            ticket_encontrado = ticket
            ticket_id_key = tid
            break

    if not ticket_encontrado:
        await interaction.response.send_message("Ticket não encontrado.", ephemeral=True)
        return

    # Atualiza o status
    ticket_encontrado["status"] = "fechado"
    ticket_encontrado["fechado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    salvar_tickets(tickets)

    # Busca o usuário dono do ticket
    usuario = guild.get_member(int(ticket_encontrado["usuario_id"]))

    # Envia log antes de deletar
    await enviar_log(
        guild, "fechado",
        ticket_encontrado["id"],
        usuario,
        ticket_encontrado["assunto"],
        interaction.user
    )

    # Avisa que vai fechar
    embed = discord.Embed(
        title="🔒 Ticket Encerrado",
        description=f"Fechado por {interaction.user.mention}\nO canal será deletado em 5 segundos.",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    await canal.send(embed=embed)

    # Aguarda e deleta o canal
    import asyncio
    await asyncio.sleep(5)
    await canal.delete(reason=f"Ticket fechado por {interaction.user.name}")


async def enviar_log(guild, acao, ticket_id, usuario, assunto, fechado_por):
    """Envia uma mensagem de log no canal de logs."""
    canal_log = discord.utils.get(guild.text_channels, name=CANAL_LOGS)
    if not canal_log:
        return

    if acao == "aberto":
        embed = discord.Embed(
            title="🟢 Novo Ticket Aberto",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
    else:
        embed = discord.Embed(
            title="🔴 Ticket Fechado",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )

    embed.add_field(name="🎫 Ticket", value=f"#{ticket_id:04d}", inline=True)
    embed.add_field(name="👤 Usuário", value=usuario.mention if usuario else "Desconhecido", inline=True)
    embed.add_field(name="📌 Assunto", value=assunto, inline=False)

    if fechado_por:
        embed.add_field(name="🔒 Fechado por", value=fechado_por.mention, inline=True)

    await canal_log.send(embed=embed)


# ============================================================
# COMANDOS SLASH
# ============================================================

@tree.command(name="setup", description="Configura o painel de suporte no canal atual")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    """Comando para admins configurarem o painel de tickets."""
    embed = discord.Embed(
        title="🎫 Central de Suporte",
        description=(
            "Precisa de ajuda? Nossa equipe está pronta para te atender!\n\n"
            "**Como funciona:**\n"
            "1️⃣ Clique no botão abaixo\n"
            "2️⃣ Preencha o formulário\n"
            "3️⃣ Aguarde nossa equipe no seu canal privado\n\n"
            "⏰ Tempo médio de resposta: **até 24 horas**"
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Clique no botão para abrir um ticket")

    await interaction.channel.send(embed=embed, view=BotaoAbrirTicket())
    await interaction.response.send_message("✅ Painel configurado!", ephemeral=True)


@tree.command(name="tickets", description="Lista todos os tickets abertos")
@app_commands.checks.has_permissions(manage_channels=True)
async def listar_tickets(interaction: discord.Interaction):
    """Lista os tickets em aberto (apenas para suporte)."""
    tickets = carregar_tickets()
    abertos = {k: v for k, v in tickets.items() if v["status"] != "fechado"}

    if not abertos:
        await interaction.response.send_message("✅ Nenhum ticket aberto!", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🎫 Tickets Abertos ({len(abertos)})",
        color=discord.Color.blurple(),
        timestamp=datetime.now()
    )

    for tid, t in list(abertos.items())[:10]:  # Máximo 10
        atendente = t["atendente"] or "Aguardando"
        embed.add_field(
            name=f"#{t['id']:04d} | {t['assunto'][:30]}",
            value=f"👤 {t['usuario_nome']} | 🔧 {atendente} | ⚡ {t['prioridade']}",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="fechar", description="Fecha o ticket do canal atual")
async def fechar_comando(interaction: discord.Interaction):
    """Comando alternativo para fechar ticket."""
    await interaction.response.send_message(
        "Tem certeza que deseja fechar o ticket?",
        view=BotaoConfirmarFechamento(),
        ephemeral=True
    )


# ============================================================
# EVENTOS DO BOT
# ============================================================

@bot.event
async def on_ready():
    """Executado quando o bot inicia."""
    print(f"✅ Bot conectado como: {bot.user}")
    print(f"🌐 Servidores: {len(bot.guilds)}")

    # Sincroniza os comandos slash direto no servidor (instantâneo!)
    try:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        print(f"⚡ {len(synced)} comandos sincronizados!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar: {e}")

    # Registra as views persistentes (botões que sobrevivem ao restart)
    bot.add_view(BotaoAbrirTicket())
    bot.add_view(BotaoControleTicket())

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="tickets de suporte 🎫"
        )
    )


@bot.event
async def on_command_error(ctx, error):
    """Trata erros de comandos."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você não tem permissão para usar este comando.")


# ============================================================
# INICIA O BOT
# ============================================================
if __name__ == "__main__":
    bot.run(TOKEN)