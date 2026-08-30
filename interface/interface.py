"""
Protótipo de TUI (Terminal User Interface) para o Jarvis, inspirado no
ncspot: navegação por atalho, visual limpo mas com personalidade, sem
parecer um terminal cru de print().

Isso é só a CASCA visual - ainda não está ligada ao motor de verdade
(jarvis.entrada.loop_conversa). O ponto de integração está marcado
claramente na função `gerar_resposta()` lá embaixo.

Rodar:
    pip install textual --break-system-packages
    python jarvis_tui_prototipo.py

Atalhos:
    Ctrl+L  - limpa a conversa
    Ctrl+M  - alterna entre modo auto / local / nuvem (só visual, por ora)
    Ctrl+Q  - sair
"""
import asyncio
import base64
import os
import random
import re
import subprocess
from datetime import datetime

import PyPDF2
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, RichLog, Static

# Imports do Jarvis (Ajuste os caminhos se necessário)
from jarvis.config import client
from jarvis.ia.motor import motor_pensamento
from jarvis.ia.visao import analisar_imagem
from jarvis.integracoes.groq_status import verificar_saude_api
from jarvis.memoria.embeddings import fatiar_e_buscar_documento
from jarvis.entrada.captura_tela import pega_print

# ==========================================
# "PERSONALIDADE" - frases de status/loading que refletem o tom do Jarvis
# (mesmo espírito do regras_base: direto, sem frescura, um pouco sarcástico)
# ==========================================

FRASES_EVENTO = {
    "interpretando_comando": "Interpretando o que você quer...",
    "buscando_memoria": "Vasculhando a memória...",
    "comprimindo_memoria": "Resumindo o que achei...",
    "pensando": "Pensando (ou fingindo que penso)...",
    "fallback_local": "Groq deu pau, chamando o cérebro local...",
    "acionando_ferramentas": "Mexendo no calendário...",
    "recebendo_confirmacao_final": "Fechando a resposta...",
    "repescagem_iniciada": "Não achei de cara, garimpando memória antiga...",
}

FRASES_PENSANDO = [
    "Pensando (ou fingindo que penso)...",
    "Consultando os astros digitais...",
    "Processando sua ideia genial...",
    "Deixa eu ver aqui...",
    "Calculando a resposta certa (ou a mais engraçada)...",
]

RESPOSTAS_DEMO = [
    "Beleza, entendi. Mas isso ainda é só o protótipo - não tô ligado no motor de verdade ainda.",
    "Olha, tecnicamente eu poderia responder isso de verdade, mas hoje sou só uma casca bonita.",
    "Anotado. Quando me conectarem no Groq/Ollama de verdade, essa resposta vai ter miolo.",
]


class PainelStatus(Static):
    """Barra lateral estilo ncspot: modo atual, latência, contador de mensagens."""

    modo = reactive("auto")
    ultima_latencia = reactive("—")
    total_mensagens = reactive(0)
    acao_atual = reactive("Aguardando...")

    def render(self) -> str:
        return (
            f"[bold cyan]STATUS[/bold cyan]\n"
            f"Modo: [bold]{self.modo}[/bold]\n"
            f"Latência: {self.ultima_latencia}\n"
            f"Mensagens: {self.total_mensagens}\n"
            f"\n[bold yellow]AÇÃO ATUAL[/bold yellow]\n"
            f"[dim italic]{self.acao_atual}[/dim italic]\n"
        )


class PainelMemoria(Static):
    """Mostra a última memória resgatada, se houver - dá o toque de 'ele lembra'."""

    ultima_memoria = reactive("Nenhuma busca ainda.")

    def render(self) -> str:
        return f"[bold magenta]MEMÓRIA[/bold magenta]\n{self.ultima_memoria}\n"


class PainelComandos(Static):
    """Referência rápida de comandos - tipo o rodapé de atalhos do ncspot."""

    def render(self) -> str:
        return (
            "[bold yellow]COMANDOS[/bold yellow]\n"
            "\\arquivo  \\print\n"
            "\\modo     \\saude\n"
            "\\multi    \\esquece\n"
        )


class JarvisTUI(App):
    """Interface de terminal do Jarvis - protótipo visual."""

    TITLE = "JARVIS"
    SUB_TITLE = "assistente de terminal"

    CSS = """
    Screen {
        background: $surface;
    }

    #corpo {
        height: 1fr;
    }

    #sidebar {
        width: 28;
        border-right: solid $accent;
        padding: 1;
    }

    #sidebar Static {
        margin-bottom: 1;
    }

    #chat-area {
        width: 1fr;
    }

    #log {
        border: round $accent;
        padding: 0 1;
        background: $surface;
    }

    #entrada {
        dock: bottom;
        margin-top: 1;
    }

    Input {
        border: round $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "limpar", "Limpar conversa"),
        Binding("ctrl+m", "alternar_modo", "Trocar modo"),
        Binding("ctrl+q", "quit", "Sair"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="corpo"):
            with Vertical(id="sidebar"):
                yield PainelStatus(id="status")
                yield PainelMemoria(id="memoria")
                yield PainelComandos(id="comandos")
            with Vertical(id="chat-area"):
                yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                yield Input(placeholder="Digite sua mensagem e aperte Enter...", id="entrada")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[bold green]Jarvis:[/bold green] E aí! Tô de pé, sem frescura. Manda a boa.")
        self.query_one("#entrada", Input).focus()

        self.motor = motor_pensamento(
            on_evento=self.evento_motor,
            on_texto=self.texto_motor
        )
        self._resposta_streaming= ""

    def evento_motor(self, tipo: str, **dados):
        status = self.query_one("#status", PainelStatus)
        memoria = self.query_one("#memoria", PainelMemoria)

        frase = FRASES_EVENTO.get(tipo)
        if frase:
            self.call_from_thread(setattr, status, "modo", status.modo)  # força refresh
            self.call_from_thread(setattr, status, "acao_atual", frase)

        if tipo == "memoria_encontrada":
            resumo = dados.get("resumo", "")[:200]
            self.call_from_thread(setattr, memoria, "ultima_memoria", resumo or "Achei algo, mas sem resumo.")
        elif tipo == "ferramenta_executada":
            self.call_from_thread(
                self.query_one("#log", RichLog).write,
                f"[dim]🛠️ {dados.get('nome')} -> {dados.get('resultado')}[/dim]",
            )
        elif tipo == "erro_nuvem" or tipo == "erro_local":
            self.call_from_thread(
                self.query_one("#log", RichLog).write,
                f"[bold red]⚠️ {dados.get('erro', 'erro desconhecido')}[/bold red]",
            )

    def texto_motor(self, pedaco: str) -> None:
        self._resposta_streaming += pedaco

    @on(Input.Submitted, "#entrada")
    async def enviar_mensagem(self, evento: Input.Submitted) -> None:
        pergunta = evento.value.strip()
        if not pergunta:
            return

        log = self.query_one("#log", RichLog)
        entrada = self.query_one("#entrada", Input)
        status = self.query_one("#status", PainelStatus)
        hora = datetime.now().strftime("%H:%M")

        entrada.value = ""
        entrada.disabled = True
        pergunta_para_motor = pergunta
        ignora_qwen = False

        # --- INTERCEPTADOR DE COMANDOS (\) ---
        if pergunta.startswith("\\"):
            partes = pergunta.split(" ", 1)
            comando = partes[0][1:].lower().strip()
            argumento = partes[1].strip() if len(partes) > 1 else ""

            if comando == "sair":
                self.exit()
                return

            elif comando == "esquece":
                self.motor.esquecer_memoria_curta()
                log.write(f"[dim italic]({hora}) 🧠 Memória de curto prazo resetada.[/dim italic]")
                entrada.disabled = False
                entrada.focus()
                return

            elif comando == "modo":
                if argumento in ["auto", "local", "nuvem"]:
                    self.motor.definir_modo(argumento)
                    status.modo = argumento
                    log.write(f"[dim italic]({hora}) ⚙️ Modo alterado para: {argumento}[/dim italic]")
                else:
                    log.write("[bold red]⚠️ Uso: \\modo auto | local | nuvem[/bold red]")
                entrada.disabled = False
                entrada.focus()
                return

            elif comando == "saude":
                status.acao_atual = "Consultando saúde Groq..."
                relatorio = await asyncio.to_thread(verificar_saude_api, client)
                log.write(f"[bold cyan]🩺 Saúde API:[/bold cyan]\n{relatorio}")
                status.acao_atual = "Aguardando..."
                entrada.disabled = False
                entrada.focus()
                return

            elif comando == "print":
                status.acao_atual = "Lendo print da tela..."
                imagem_endereco = await asyncio.to_thread(pega_print)
                if imagem_endereco is None:
                    log.write("[bold red]⚠️ Nenhuma print encontrada na pasta.[/bold red]")
                    entrada.disabled = False
                    entrada.focus()
                    return

                extensao = os.path.splitext(imagem_endereco)[1].lower()
                with open(imagem_endereco, "rb") as img_file:
                    img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

                conteudo_imagem, origem = await asyncio.to_thread(analisar_imagem, imagem_endereco, extensao,
                                                                  img_base64)
                if origem == "erro":
                    log.write(f"[bold red]❌ Erro na visão: {conteudo_imagem}[/bold red]")
                    entrada.disabled = False
                    entrada.focus()
                    return

                fonte = "Ollama" if origem == "local" else "Groq"
                pergunta_para_motor = (f"Transcrição de imagem lida por {fonte}:\n\n{conteudo_imagem}\n\n"
                                       "Analise esse conteúdo e me pergunte como deseja prosseguir.")
                ignora_qwen = True

            elif comando == "arquivo":
                if not argumento:
                    log.write("[bold red]⚠️ Forneça o caminho do arquivo. Ex: \\arquivo C:\\caminho.pdf[/bold red]")
                    entrada.disabled = False
                    entrada.focus()
                    return

                caminho = argumento.strip('"').strip("'")
                extensao = os.path.splitext(caminho)[1].lower()
                status.acao_atual = f"Carregando {extensao}..."

                try:
                    if extensao == ".pdf":
                        leitura_arquivo = ""
                        with open(caminho, "rb") as arquivo:
                            leitor_pdf = PyPDF2.PdfReader(arquivo)
                            for pagina in leitor_pdf.pages:
                                txt = pagina.extract_text()
                                if txt: leitura_arquivo += txt + "\n"

                        log.write(f"[dim]PDF carregado. {len(leitura_arquivo)} caracteres.[/dim]")
                        # Na TUI, para evitar bloquear pedindo o que buscar, passamos direto pro RAG um comando genérico
                        # Ou você pode pedir pro usuário colocar na mesma linha: \arquivo C:\doc.pdf resumo
                        # Aqui faremos um fallback genérico para não travar a UI:
                        trechos = await asyncio.to_thread(fatiar_e_buscar_documento, leitura_arquivo,
                                                          "resumo principal", 3)
                        pergunta_para_motor = f"Arquivo enviado: {caminho}.\nCom base nos trechos:\n{trechos}\nFaça um resumo geral do que se trata."
                        ignora_qwen = True

                    elif extensao in [".txt", ".md"]:
                        with open(caminho, "r", encoding="utf-8") as f:
                            conteudo = f.read()
                        pergunta_para_motor = f"Arquivo enviado ({caminho}).\nConteúdo:\n{conteudo[:4000]}\nAnalise o arquivo."
                        ignora_qwen = True

                    else:
                        log.write(f"[bold red]⚠️ Arquivo não suportado pela TUI no momento: {extensao}[/bold red]")
                        entrada.disabled = False
                        entrada.focus()
                        return

                except Exception as e:
                    log.write(f"[bold red]❌ Erro ao ler arquivo: {e}[/bold red]")
                    entrada.disabled = False
                    entrada.focus()
                    return

            else:
                log.write(f"[bold red]⚠️ Comando inválido.[/bold red]")
                entrada.disabled = False
                entrada.focus()
                return
        # ---------------------------------------------

        log.write(f"[bold blue]Você[/bold blue] [dim]({hora})[/dim]: {pergunta}")

        status.acao_atual = random.choice(FRASES_PENSANDO)
        inicio = asyncio.get_event_loop().time()

        try:
            self._resposta_streaming = ""
            self.motor.definir_modo(status.modo)
            resultado = await asyncio.to_thread(self.motor.processar, pergunta_para_motor, ignora_intencao = ignora_qwen)
            resposta = resultado["resposta_formatada"]
        except Exception as erro:
            resposta = f"[bold red]Falha no processamento: {erro}[/bold red]"

        duracao = asyncio.get_event_loop().time() - inicio

        log.write(f"[bold green]Jarvis:[/bold green] {resposta}")

        status.ultima_latencia = f"{duracao:.2f}s"
        status.total_mensagens += 1
        status.acao_atual = "Aguardando..."
        entrada.disabled = False
        entrada.focus()

    def action_limpar(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_alternar_modo(self) -> None:
        status = self.query_one("#status", PainelStatus)
        ordem = ["auto", "local", "nuvem"]
        novo_modo = ordem[(ordem.index(status.modo)+1)% len(ordem)]
        status.modo = novo_modo
        self.motor.definir_modo(novo_modo)

if __name__ == "__main__":
    JarvisTUI().run()