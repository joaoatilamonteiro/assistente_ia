"""
Controle de mouse/teclado do Jarvis (RPA / "computer use"), via pyautogui.

qualquer ação classificada como "enviar", "deletar",
"instalar" ou "fechar" passa por confirmação no terminal ANTES de
executar. Essa checagem está no codigo (dicionário CATEGORIA_ACAO +
`if` em executar_acao_pc), não é uma instrução que a IA pode escolher
seguir ou ignorar — mesmo que o modelo "decida" pular, o Python não deixa.

Toda ação (sensível ou não) imprime uma descrição detalhada do que vai
fazer, montada a partir dos argumentos reais recebidos (não do texto que
a IA escreveu) — assim a descrição sempre bate com o que de fato roda.
"""
import os
import subprocess
import time

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # isolar o mouse no canto superior esquerdo aborta a ação em andamento
    pyautogui.PAUSE = 0.15
    _PYAUTOGUI_OK = True
except Exception as _erro_import:
    _PYAUTOGUI_OK = False
    _ERRO_IMPORT = _erro_import


def _checar_pyautogui():
    if not _PYAUTOGUI_OK:
        raise RuntimeError(f"pyautogui indisponível neste ambiente: {_ERRO_IMPORT}")


# --------------------------------------------------------------------
# Categorias sensíveis. Se o nome da ação não está aqui como None,
# ela SEMPRE pede confirmação — sem exceção, sem bypass por argumento.
# --------------------------------------------------------------------
CATEGORIA_ACAO = {
    "mover_mouse": None,
    "clicar": None,
    "digitar_texto": None,
    "pressionar_tecla": None,
    "tirar_screenshot": None,

    "enviar_texto_e_enter": "enviar",
    "deletar_arquivo": "deletar",
    "instalar_pacote": "instalar",
    "fechar_janela_ativa": "fechar",
}


# --------------------------------------------------------------------
# Ações de verdade
# --------------------------------------------------------------------
def mover_mouse(x, y, duracao=0.3):
    _checar_pyautogui()
    pyautogui.moveTo(x, y, duration=duracao)
    return f"Mouse movido para ({x}, {y})."


def clicar(x=None, y=None, botao="left"):
    _checar_pyautogui()
    if x is not None and y is not None:
        pyautogui.moveTo(x, y, duration=0.2)
    pyautogui.click(button=botao)
    local = f"({x}, {y})" if x is not None else "na posição atual do cursor"
    return f"Cliquei ({botao}) em {local}."


def digitar_texto(texto, intervalo=0.03):
    _checar_pyautogui()
    pyautogui.write(texto, interval=intervalo)
    return f"Digitei o texto ({len(texto)} caracteres)."


def pressionar_tecla(tecla):
    """Aceita uma tecla única ('enter') ou um atalho combinado com '+' ('ctrl+s')."""
    _checar_pyautogui()
    partes = [p.strip() for p in tecla.lower().split("+")]
    if len(partes) > 1:
        pyautogui.hotkey(*partes)
    else:
        pyautogui.press(partes[0])
    return f"Pressionei: {tecla}."


def tirar_screenshot():
    _checar_pyautogui()
    pasta = os.path.join(os.path.expanduser("~"), "jarvis_screenshots_controle")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f"controle_{int(time.time())}.png")
    pyautogui.screenshot(caminho)
    return caminho


# --- Ações sensíveis (sempre confirmadas — ver CATEGORIA_ACAO) ---

def enviar_texto_e_enter(texto):
    """Digita um texto e aperta Enter - padrão de 'enviar' (mensagem, comando, formulário)."""
    _checar_pyautogui()
    pyautogui.write(texto, interval=0.03)
    pyautogui.press("enter")
    return f"Enviado (digitado + Enter): \"{texto[:80]}{'...' if len(texto) > 80 else ''}\""


def deletar_arquivo(caminho):
    if not os.path.exists(caminho):
        return f"Arquivo não encontrado, nada foi apagado: {caminho}"
    tamanho = os.path.getsize(caminho)
    os.remove(caminho)
    return f"Apagado: {caminho} ({tamanho} bytes)."


def instalar_pacote(nome_pacote, gerenciador="pip"):
    comandos = {
        "pip": ["pip", "install", nome_pacote, "--break-system-packages"],
        "winget": ["winget", "install", nome_pacote],
        "choco": ["choco", "install", nome_pacote, "-y"],
    }
    comando = comandos.get(gerenciador)
    if not comando:
        return f"Gerenciador desconhecido: {gerenciador}. Use 'pip', 'winget' ou 'choco'."

    resultado = subprocess.run(comando, capture_output=True, text=True, timeout=300)
    if resultado.returncode == 0:
        return f"Instalado com sucesso via {gerenciador}: {nome_pacote}"
    return f"Falha ao instalar {nome_pacote} via {gerenciador}: {resultado.stderr[-500:]}"


def fechar_janela_ativa():
    """Fecha a janela em foco via Alt+F4 (Windows)."""
    _checar_pyautogui()
    pyautogui.hotkey("alt", "f4")
    return "Fechei a janela ativa (Alt+F4)."


_FUNCOES_ACAO = {
    "mover_mouse": mover_mouse,
    "clicar": clicar,
    "digitar_texto": digitar_texto,
    "pressionar_tecla": pressionar_tecla,
    "tirar_screenshot": tirar_screenshot,
    "enviar_texto_e_enter": enviar_texto_e_enter,
    "deletar_arquivo": deletar_arquivo,
    "instalar_pacote": instalar_pacote,
    "fechar_janela_ativa": fechar_janela_ativa,
}


def _descrever_acao(nome, args):
    """Monta a descrição detalhada a partir dos argumentos DE VERDADE que
    vão ser usados na execução - não do que a IA disse em texto livre."""
    if nome == "mover_mouse":
        return f"Mover o mouse para ({args.get('x')}, {args.get('y')})."
    if nome == "clicar":
        local = f"({args.get('x')}, {args.get('y')})" if args.get("x") is not None else "na posição atual do cursor"
        return f"Clicar com o botão '{args.get('botao', 'left')}' em {local}."
    if nome == "digitar_texto":
        texto = args.get("texto", "")
        return f"Digitar: \"{texto[:120]}{'...' if len(texto) > 120 else ''}\" ({len(texto)} caracteres)."
    if nome == "pressionar_tecla":
        return f"Pressionar a tecla/atalho: {args.get('tecla')}."
    if nome == "tirar_screenshot":
        return "Tirar um screenshot da tela atual."
    if nome == "enviar_texto_e_enter":
        texto = args.get("texto", "")
        return (f"⚠️ ENVIAR: digitar \"{texto[:120]}{'...' if len(texto) > 120 else ''}\" e apertar Enter "
                f"(isso pode mandar uma mensagem, comando ou formulário de verdade).")
    if nome == "deletar_arquivo":
        caminho = args.get("caminho", "")
        existe = os.path.exists(caminho)
        detalhe = f"{os.path.getsize(caminho)} bytes" if existe else "ARQUIVO NÃO ENCONTRADO"
        return f"⚠️ DELETAR PERMANENTEMENTE: {caminho} ({detalhe})."
    if nome == "instalar_pacote":
        return f"⚠️ INSTALAR: '{args.get('nome_pacote')}' via {args.get('gerenciador', 'pip')}."
    if nome == "fechar_janela_ativa":
        return "⚠️ FECHAR a janela atualmente em foco (Alt+F4)."
    return f"Executar '{nome}' com argumentos: {args}"


def _confirmar_no_terminal(descricao, categoria):
    print(f"\n{'=' * 60}")
    print(f"🔒 CONFIRMAÇÃO NECESSÁRIA — categoria: {categoria.upper()}")
    print(descricao)
    print("=" * 60)
    resposta = input("Autorizar essa ação? ('s' confirma, qualquer outra tecla cancela): ").strip().lower()
    return resposta == "s"


def executar_acao_pc(nome, argumentos, confirmar=_confirmar_no_terminal):
    """Ponto de entrada único: main.py e loop_conversa.py chamam só isso.
    Sempre imprime a descrição. Ações enviar/deletar/instalar/fechar
    SEMPRE passam por `confirmar` antes de rodar - não é opcional."""
    if nome not in CATEGORIA_ACAO:
        return f"❌ Ação desconhecida: {nome}"

    descricao = _descrever_acao(nome, argumentos)
    print(f"\n🖱️ [CONTROLE PC] {descricao}")

    categoria = CATEGORIA_ACAO[nome]
    if categoria is not None and not confirmar(descricao, categoria):
        return f"❌ Ação '{nome}' (categoria: {categoria}) CANCELADA pelo usuário."

    try:
        return _FUNCOES_ACAO[nome](**argumentos)
    except Exception as e:
        return f"❌ Erro ao executar '{nome}': {e}"


# --------------------------------------------------------------------
# Schema de tools (mesmo formato de ferramentas_jarvis, pra combinar
# as duas listas na chamada da Groq/Ollama)
# --------------------------------------------------------------------
ferramentas_controle_pc = [
    {
        "type": "function",
        "function": {
            "name": "mover_mouse",
            "description": "Move o cursor do mouse para uma posição X,Y na tela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Posição horizontal em pixels."},
                    "y": {"type": "integer", "description": "Posição vertical em pixels."},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clicar",
            "description": "Clica com o mouse. Se x/y forem informados, move até lá antes de clicar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Posição horizontal (opcional)."},
                    "y": {"type": "integer", "description": "Posição vertical (opcional)."},
                    "botao": {"type": "string", "enum": ["left", "right", "middle"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "digitar_texto",
            "description": "Digita um texto no campo/janela em foco, SEM apertar Enter.",
            "parameters": {
                "type": "object",
                "properties": {"texto": {"type": "string", "description": "Texto a digitar."}},
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pressionar_tecla",
            "description": "Pressiona uma tecla ou atalho (ex: 'enter', 'esc', 'ctrl+s', 'alt+tab').",
            "parameters": {
                "type": "object",
                "properties": {"tecla": {"type": "string"}},
                "required": ["tecla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tirar_screenshot",
            "description": "Tira um screenshot da tela inteira e salva em disco, retornando o caminho.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_texto_e_enter",
            "description": "[REQUER CONFIRMAÇÃO] Digita um texto e pressiona Enter - usado pra ENVIAR mensagens, comandos ou formulários.",
            "parameters": {
                "type": "object",
                "properties": {"texto": {"type": "string", "description": "Texto a enviar."}},
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deletar_arquivo",
            "description": "[REQUER CONFIRMAÇÃO] Apaga permanentemente um arquivo do disco.",
            "parameters": {
                "type": "object",
                "properties": {"caminho": {"type": "string", "description": "Caminho absoluto do arquivo."}},
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "instalar_pacote",
            "description": "[REQUER CONFIRMAÇÃO] Instala um pacote/programa via pip, winget ou choco.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_pacote": {"type": "string"},
                    "gerenciador": {"type": "string", "enum": ["pip", "winget", "choco"]},
                },
                "required": ["nome_pacote"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fechar_janela_ativa",
            "description": "[REQUER CONFIRMAÇÃO] Fecha a janela atualmente em foco (Alt+F4).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

NOMES_ACOES_PC = set(CATEGORIA_ACAO.keys())
