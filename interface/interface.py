import asyncio
import base64
import os
import random
from datetime import datetime
import ctypes


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
from jarvis.utils.motor_latex import latex_para_unicode
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
    "acionando_ferramentas": "Executando ferramenta(s)...",
    "recebendo_confirmacao_final": "Fechando a resposta...",
    "repescagem_iniciada": "Não achei de cara, garimpando memória antiga...",
}

FRASES_FERRAMENTA = {
    #calendario
    "adicionar_multiplos_eventos": "Criando evento(s) na agenda...",
    "apagar_eventos_por_termo": "Apagando evento(s) da agenda...",
    "editar_evento_por_termo": "Editando evento na agenda...",
    "listar_proximos_eventos": "Consultando a agenda...",
    #controle do pc
    "mover_mouse": "Movendo o mouse...",
    "clicar": "Clicando na tela...",
    "digitar_texto": "Digitando no teclado...",
    "pressionar_tecla": "Apertando uma tecla...",
    "tirar_screenshot": "Tirando um print da tela...",
    "enviar_texto_e_enter": "Enviando texto e apertando Enter...",
    "deletar_arquivo": "Mexendo pra deletar um arquivo...",
    "instalar_pacote": "Instalando um pacote...",
    "fechar_janela_ativa": "Fechando a janela em foco...",
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
        Binding("ctrl+s", "enviar", "Enviar mensagem", priority=True)
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
                yield TextArea(placeholder="Digite sua mensagem e aperte Enter...", id="entrada")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[bold green]Adomo:[/bold green] E aí! Tô de pé, sem frescura. Manda a boa.")
        self.query_one("#entrada", TextArea).focus()

        self.motor = motor_pensamento(
            on_evento=self.evento_motor,
            on_texto=self.texto_motor,
            confirmar_pc = self.confirmar_acao_pc,
        )
        self._resposta_streaming= None
        self._confirmacao_pendente = None

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
        duracao = asyncio.get_event_loop().time() - inicio
        log.write(f"[bold green]Adomo[/bold green] [dim]({hora})[/dim]:")
        if houve_erro:
            log.write(resposta)
        else:
            resposta_limpa = re.sub(r"<br\s*/?>", "\n", resposta, flags=re.IGNORECASE)
            resposta_limpa = latex_para_unicode(resposta_limpa)
            log.write(Markdown(resposta_limpa))
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