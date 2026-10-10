import asyncio
import base64
import os
import random
from datetime import datetime
import ctypes
import json
from jarvis.config import ARQUIVO_TEXTOS_INTERFACE


import PyPDF2
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.containers import Vertical
from textual.widgets import Footer, Header, RichLog, Static, TextArea

# Imports do Jarvis (Ajuste os caminhos se necessário)
from jarvis.config import client
from jarvis.ia.motor import motor_pensamento
from jarvis.ia.visao import analisar_imagem
from jarvis.integracoes.groq_status import verificar_saude_api
from jarvis.entrada.captura_tela import pega_print

import threading
import re
from rich.markdown import Markdown
from rich.text import Text
from jarvis.utils.motor_latex import latex_para_unicode
# ==========================================
# "PERSONALIDADE" - frases de status/loading que refletem o tom do Jarvis
# (mesmo espírito do regras_base: direto, sem frescura, um pouco sarcástico)
# ==========================================

with open(ARQUIVO_TEXTOS_INTERFACE, "r", encoding="utf-8") as _f:
    _textos = json.load(_f)

FRASES_EVENTO = _textos["frases_evento"]
FRASES_FERRAMENTA = _textos["frases_ferramenta"]
FRASES_PENSANDO = _textos["frases_pensando"]



def markup_para_texto_plano(markup: str) -> str:
    """Tira as tags de formatação do Rich ([bold red]...[/bold red]) e devolve só o texto.
    Usa o parser do próprio Rich em vez de regex, pra não comer colchetes que são
    parte do texto (ex: '[Errno 11001]')."""
    try:
        return Text.from_markup(markup).plain
    except Exception:
        return re.sub(r"\[/?[a-z#@][^\[\]]*\]", "", markup)


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


class LogSelecionavel(TextArea):
    """
    TextArea somente-leitura usada como 'visão alternativa' do histórico da
    conversa. Existe só por um motivo: o RichLog não suporta seleção de texto
    nativamente (limitação conhecida e ainda em aberto do próprio Textual),
    enquanto o TextArea já suporta - dá pra arrastar o mouse ou usar
    Shift+setas pra selecionar normalmente.

    Ctrl+C aqui dentro copia a seleção (ou tudo, se nada estiver selecionado)
    pra área de transferência do sistema via OSC 52 (mesmo mecanismo do
    action_copiar_resposta lá no App).
    """

    BINDINGS = [
        Binding("ctrl+c", "copiar_selecao", "Copiar seleção", priority=True),
    ]

    def on_mount(self) -> None:
        self.read_only = True
        self.show_line_numbers = False

    def action_copiar_selecao(self) -> None:
        texto = self.selected_text or self.text
        if not texto:
            self.app.notify("Nada pra copiar ainda.", title="Copiar", severity="warning")
            return
        self.app.copy_to_clipboard(texto)
        self.app.notify(f"{len(texto)} caracteres copiados!", title="📋 Copiado")




class JarvisTUI(App):

    TITLE = "Adomo"
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

    #log-select {
        border: round $warning;
        display: none;
    }

    #entrada {
        dock: bottom;
        margin-top: 1;
        height: 5;
        border: round $accent;
    }

    """

    BINDINGS = [
        Binding("ctrl+l", "limpar", "Limpar conversa"),
        Binding("ctrl+t", "alternar_modo", "Trocar modo"),
        Binding("ctrl+q", "quit", "Sair"),
        Binding("ctrl+s", "enviar", "Enviar mensagem", priority=True),
        Binding("ctrl+e", "cancelar", "Cancelar ação", priority=True),
        Binding("ctrl+y", "copiar_resposta", "Copiar última resposta", priority=True),
        Binding("ctrl+r", "alternar_selecao", "Selecionar texto", priority=True),
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
                yield LogSelecionavel(id="log-select", language="markdown")
                yield TextArea(placeholder="Digite sua mensagem e aperte Enter...", id="entrada")
        yield Footer()

    def on_mount(self) -> None:
        self._transcript_texto = ""  # histórico em texto puro (sem tags Rich) pro modo seleção (Ctrl+R)
        self.escrever_log("[bold green]Adomo:[/bold green] E aí! Tô de pé, sem frescura. Manda a boa.")
        self.query_one("#entrada", TextArea).focus()

        self.motor = motor_pensamento(
            on_evento=self.evento_motor,
            on_texto=self.texto_motor,
            confirmar_pc = self.confirmar_acao_pc,
        )
        self._resposta_streaming= None
        self._confirmacao_pendente = None
        self._ultima_resposta_texto = None  # guarda o texto pra o atalho Ctrl+Y copiar

    def confirmar_acao_pc(self, descricao: str, categoria: str) -> bool:
        """Abre uma caixa de diálogo NATIVA do Windows (fora do Textual),
        bloqueando essa thread até o usuário clicar Sim ou Não.
        Como é uma janela do próprio Windows, sempre responde a mouse/teclado,
        sem depender do event loop da TUI."""
        MB_YESNO = 0x04
        MB_ICONWARNING = 0x30
        MB_TOPMOST = 0x40000  # garante que a janela aparece na frente de tudo

        texto = f"{descricao}\n\nAutorizar essa ação?"
        resultado = ctypes.windll.user32.MessageBoxW(
            0, texto, f"🔒 Confirmação necessária — {categoria.upper()}",
            MB_YESNO | MB_ICONWARNING | MB_TOPMOST,
        )
        IDYES = 6
        return resultado == IDYES


    def escrever_log(self, markup: str) -> None:
        """Escreve no log colorido E guarda a versão em texto puro na transcrição
        (é a que aparece no modo Ctrl+R). Roda na thread principal - de dentro da
        thread do motor, chame via self.call_from_thread(self.escrever_log, ...)."""
        self.query_one("#log", RichLog).write(markup)
        self._transcript_texto += markup_para_texto_plano(markup) + "\n\n"

    def evento_motor(self, tipo: str, **dados):
        status = self.query_one("#status", PainelStatus)
        memoria = self.query_one("#memoria", PainelMemoria)

        if tipo == "acionando_ferramentas":
            nome = dados.get("ferramentas", [])
            frases_encontradas = [FRASES_FERRAMENTA.get(n, f"executando '{n}'...")for n in nome]
            frase = " / ".join(dict.fromkeys(frases_encontradas)) if frases_encontradas else FRASES_EVENTO.get(tipo)
        else:
            frase = FRASES_EVENTO.get(tipo)

        if frase:
            self.call_from_thread(setattr, status, "modo", status.modo)  # força refresh
            self.call_from_thread(setattr, status, "acao_atual", frase)

        if tipo == "memoria_encontrada":
            resumo = dados.get("resumo", "")[:200]
            self.call_from_thread(setattr, memoria, "ultima_memoria", resumo or "Achei algo, mas sem resumo.")
        elif tipo == "ferramenta_repetida":
            self.call_from_thread(
                self.escrever_log,
                f"[bold yellow]⚠️ '{dados.get('nome')}' foi chamada {dados.get('vezes')}x nesta resposta[/bold yellow]",
            )
        elif tipo == "erro_nuvem" or tipo == "erro_local":
            self.call_from_thread(
                self.escrever_log,
                f"[bold red]⚠️ {dados.get('erro', 'erro desconhecido')}[/bold red]",
            )

    def texto_motor(self, pedaco: str) -> None:
        self._resposta_streaming += pedaco

    async def action_enviar(self) -> None:
        entrada = self.query_one("#entrada",TextArea)
        if entrada.disabled:
            return
        pergunta = entrada.text.strip()
        if not pergunta:
            return

        log = self.query_one("#log", RichLog)
        status = self.query_one("#status", PainelStatus)
        hora = datetime.now().strftime("%H:%M")

        seletor = self.query_one("#log-select", LogSelecionavel)
        if seletor.styles.display != "none":
            # Estava no modo seleção - volta pro log normal antes de mandar,
            # senão a resposta nova fica escondida atrás do TextArea.
            seletor.styles.display = "none"
            log.styles.display = "block"

        entrada.text = ""
        entrada.disabled = True

        pergunta_para_motor = pergunta
        ignora_qwen = False

        # --- INTERCEPTADOR DE COMANDOS (\) ---
        if pergunta.startswith("\\"):
            partes = pergunta.split(" ", 1)
            comando = partes[0][1:].lower().strip()
            argumento = partes[1].strip() if len(partes)  > 1 else ""
            if comando == "sair":
                self.exit()
                return

            elif comando == "esquece":
                self.motor.esquecer_memoria_curta()
                self.escrever_log(f"[dim italic]({hora}) 🧠 Memória de curto prazo resetada.[/dim italic]")
                entrada.disabled = False
                entrada.focus()
                return

            elif comando == "modo":
                if argumento in ["auto", "local", "nuvem"]:
                    self.motor.definir_modo(argumento)
                    status.modo = argumento
                    self.escrever_log(f"[dim italic]({hora}) ⚙️ Modo alterado para: {argumento}[/dim italic]")
                else:
                    self.escrever_log("[bold red]⚠️ Uso: \\modo auto | local | nuvem[/bold red]")
                entrada.disabled = False
                entrada.focus()
                return

            elif comando == "saude":
                status.acao_atual = "Consultando saúde Groq..."
                relatorio = await asyncio.to_thread(verificar_saude_api, client)
                self.escrever_log(f"[bold cyan]🩺 Saúde API:[/bold cyan]\n{relatorio}")
                status.acao_atual = "Aguardando..."
                entrada.disabled = False
                entrada.focus()
                return

            elif comando == "print":
                status.acao_atual = "Lendo print da tela..."
                imagem_endereco = await asyncio.to_thread(pega_print)
                if imagem_endereco is None:
                    self.escrever_log("[bold red]⚠️ Nenhuma print encontrada na pasta.[/bold red]")
                    entrada.disabled = False
                    entrada.focus()
                    return

                extensao = os.path.splitext(imagem_endereco)[1].lower()
                with open(imagem_endereco, "rb") as img_file:
                    img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

                conteudo_imagem, origem = await asyncio.to_thread(analisar_imagem, imagem_endereco, extensao,
                                                                  img_base64)
                if origem == "erro":
                    self.escrever_log(f"[bold red]❌ Erro na visão: {conteudo_imagem}[/bold red]")
                    entrada.disabled = False
                    entrada.focus()
                    return

                fonte = "Ollama" if origem == "local" else "Groq"
                pergunta_para_motor = (f"Transcrição de imagem lida por {fonte}:\n\n{conteudo_imagem}\n\n"
                                       "Analise esse conteúdo e me pergunte como deseja prosseguir.")
                ignora_qwen = True



            else:
                self.escrever_log(f"[bold red]⚠️ Comando inválido.[/bold red]")
                entrada.disabled = False
                entrada.focus()
                return
        # ---------------------------------------------

        log.write(f"[bold blue]Você[/bold blue] [dim]({hora})[/dim]: {pergunta}")
        self._transcript_texto += f"Você ({hora}): {pergunta}\n\n"

        status.acao_atual = random.choice(FRASES_PENSANDO)

        try:
            self._resposta_streaming = ""
            self.motor.definir_modo(status.modo)
            resultado_container = {}
            erro_container = {}

            def _rodar_motor():
                try:
                    resultado_container["valor"] = self.motor.processar(pergunta_para_motor,
                                                                        ignora_intencao=ignora_qwen)
                except Exception as e:
                    erro_container["valor"] = e

            thread = threading.Thread(target=_rodar_motor, daemon=True)
            thread.start()
            while thread.is_alive():
                await asyncio.sleep(0.05)

            if "valor" in erro_container:
                raise erro_container["valor"]
            resultado = resultado_container["valor"]

            resposta = resultado["resposta_formatada"]
            houve_erro = False
        except Exception as erro:
            resposta = f"[bold red]Falha no processamento: {erro}[/bold red]"
            houve_erro = True
        duracao = resultado.get("duracao",0) if not houve_erro else 0
        log.write(f"[bold green]Adomo[/bold green] [dim]({hora})[/dim]:")
        if houve_erro:
            log.write(resposta)
            self._transcript_texto += f"Adomo ({hora}) [erro]: {markup_para_texto_plano(resposta)}\n\n"
        else:
            resposta_limpa = re.sub(r"<br\s*/?>", "\n", resposta, flags=re.IGNORECASE)
            resposta_limpa = latex_para_unicode(resposta_limpa)
            log.write(Markdown(resposta_limpa))
            self._ultima_resposta_texto = resposta_limpa  # disponível pro Ctrl+Y
            self._transcript_texto += f"Adomo ({hora}): {resposta_limpa}\n\n"
        status.ultima_latencia = f"{duracao:.2f}s"
        status.total_mensagens += 1
        status.acao_atual = "Aguardando..."
        entrada.disabled = False
        entrada.focus()

    def action_limpar(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_copiar_resposta(self) -> None:
        """Copia a última resposta do Adomo pra área de transferência do sistema.
        Usa App.copy_to_clipboard (OSC 52) - funciona até em SSH/tmux, sem
        precisar arrastar o mouse pra selecionar texto (o RichLog não suporta
        seleção nativa - é uma limitação conhecida do próprio Textual)."""
        log = self.query_one("#log", RichLog)
        if not self._ultima_resposta_texto:
            log.write("[dim italic]Nada pra copiar ainda.[/dim italic]")
            return
        self.copy_to_clipboard(self._ultima_resposta_texto)
        self.notify("Última resposta copiada!", title="📋 Copiado")

    def action_alternar_selecao(self) -> None:
        """Alterna entre o RichLog (bonito, sem seleção) e o LogSelecionavel
        (texto puro, com seleção nativa de verdade). Ctrl+R de novo (ou
        mandar uma mensagem) volta pro modo normal."""
        log = self.query_one("#log", RichLog)
        seletor = self.query_one("#log-select", LogSelecionavel)
        entrada = self.query_one("#entrada", TextArea)

        entrando_em_modo_selecao = seletor.styles.display == "none"

        if entrando_em_modo_selecao:
            seletor.text = self._transcript_texto or "(nada pra mostrar ainda)"
            log.styles.display = "none"
            seletor.styles.display = "block"
            seletor.focus()
        else:
            seletor.styles.display = "none"
            log.styles.display = "block"
            entrada.focus()

    def action_cancelar(self) -> None:
        if hasattr(self, "motor"):
            self.motor.cancelar()
            log = self.query_one("#log", RichLog)
            self.escrever_log("[dim italic]Cancelamento solicitado — parando assim que possível...[/dim italic]")

    def action_alternar_modo(self) -> None:
        status = self.query_one("#status", PainelStatus)
        ordem = ["auto", "local", "nuvem"]
        novo_modo = ordem[(ordem.index(status.modo)+1)% len(ordem)]
        status.modo = novo_modo
        self.motor.definir_modo(novo_modo)

if __name__ == "__main__":
    JarvisTUI().run()