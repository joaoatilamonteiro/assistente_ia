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
import base64
import os
import subprocess
import tempfile
import time
import inspect
import webbrowser

from jarvis.ia.visao import analisar_imagem
from jarvis.memoria.embeddings import fatiar_e_buscar_documento
import PyPDF2

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
    "ler_arquivo": None,
    "mover_mouse": None,
    "clicar": None,
    "abrir_url": None,
    "digitar_texto": None,
    "pressionar_tecla": None,
    "tirar_screenshot": None,
    "posicao_mouse_atual": None,
    "localizar_na_tela": None,
    "listar_arquivos": None,

    "criar_arquivo": "criar",
    "abrir_programa": "abrir",
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
def posicao_mouse_atual():
    _checar_pyautogui()
    x, y = pyautogui.position()
    return f"O mouse está atualmente em ({x}, {y})."

def localizar_na_tela(descricao_alvo):
    """Tira um screenshot temporário e pede pro modelo de visão estimar
    a posição (x, y) aproximada de um elemento na tela."""
    _checar_pyautogui()
    caminho = _tirar_print_temporaria()
    try:
        largura, altura = pyautogui.size()
        with open(caminho, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            f"Esta captura de tela tem resolução {largura}x{altura} pixels, "
            f"origem (0,0) no canto SUPERIOR ESQUERDO. "
            f"Localize o elemento: \"{descricao_alvo}\". "
            f"Responda APENAS no formato: X,Y (coordenadas de pixel do centro do elemento). "
            f"Se não encontrar, responda: NAO_ENCONTRADO."
        )
        resultado, origem = analisar_imagem(caminho, ".png", img_base64, prompt=prompt)
        return resultado
    finally:
        if os.path.exists(caminho):
            os.remove(caminho)

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

def abrir_programa(caminho_nome):
    try:
        os.startfile(caminho_nome)
        return f"abri:{caminho_nome}"
    except FileNotFoundError:
        try:
            subprocess.Popen(caminho_nome, shell=True)
            return f"abri: {caminho_nome}"
        except Exception as e:
            return f"Não consegui abrir '{caminho_nome}'\nerror: {e}"

def abrir_url(url):
    if "://" not in url:
        url = "https://"+url

    webbrowser.open(url)
    resultado_verificacao, origem = verificar_abertura(f"o site {url} carregado no navegador")
    return f"Abri {url} no navegador padrão. Verificação visual ({origem}): {resultado_verificacao}"

def _tirar_print_temporaria():
    _checar_pyautogui()
    fd, caminho = tempfile.mkstemp(suffix=".png", prefix="verificacao_")
    os.close(fd)
    pyautogui.screenshot(caminho)
    return caminho

def verificar_abertura(descricao_esperada, espera_segundos = 2.5):
    _checar_pyautogui()
    time.sleep(espera_segundos)
    caminho = _tirar_print_temporaria()
    try:
        with open(caminho,"rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")

        prompt_verificacao  = (
            f"Esta é uma captura de tela ATUAL do computador do usuário. "
            f"Verifique se ela mostra evidência de que o seguinte está aberto ou "
            f"visível na tela agora: \"{descricao_esperada}\". "
            f"Responda começando com 'SIM' ou 'NÃO' em maiúsculas, seguido de uma "
            f"frase curta explicando o que você vê na tela que te levou a essa conclusão."
        )
        resultado,origem = analisar_imagem(caminho,".png",img_base64, prompt = prompt_verificacao)
        return resultado, origem

    finally: #nao sabia dessa, ela executa independente o que aconteça, com erro ou nao ela vai tentar exlcuir o arquivo
        if os.path.exists(caminho):
            os.remove(caminho)


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

def ler_arquivo(caminho, pergunta_busca = "resumo principal"):
    if not os.path.exists(caminho):
        return f"arquivo nao encontrado {caminho}"
    extensao = os.path.splitext(caminho)[1].lower()

    try:
        if extensao == ".pdf":
            leitura_arquivo = ""
            with open(caminho, "rb") as arquivo:
                leitor_pdf = PyPDF2.PdfReader(arquivo)
                for pagina in leitor_pdf.pages:
                    txt = pagina.extract_text()
                    if txt:
                        leitura_arquivo += txt + "\n"
            trechos = fatiar_e_buscar_documento(leitura_arquivo, pergunta_busca, 3)
            return f"PDF lido ({len(leitura_arquivo)} caracteres). Trechos relevantes:\n{trechos}"

        elif extensao in (".txt", ".md", ".html", ".htm", ".py", ".js", ".css", ".json", ".csv"):
            with open(caminho, "r", encoding="utf-8") as f:
                conteudo = f.read()
            return conteudo[:8000]  # limite de segurança pro contexto

        else:
            return f"Tipo de arquivo não suportado ainda: '{extensao}'. Suportados: .pdf, .txt, .md, .html, .py, .js, .css, .json, .csv."

    except Exception as e:
        return f"erro ao ler o arquivo '{caminho}\nerro:{e}'"

def listar_arquivos(pasta):
    try:
        itens = os.listdir(pasta)
        if not itens:
            return f"A pasta '{pasta}' está vazia."
        return "\n".join(itens)
    except Exception as e:
        return f"Erro ao listar '{pasta}': {e}"

def criar_arquivo(caminho, conteudo =""):
    try:
        pasta = os.path.dirname(caminho)
        if pasta and not os.path.exists(pasta):
            os.makedirs(pasta, exist_ok= True)
        with open (caminho, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return f"arquivo criado: {caminho} ({len(conteudo)}) caracteres."
    except Exception as e:
        return f"erro ao criar arquivo no caminho: {caminho}\nerro:{e}"

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
    "listar_arquivos": listar_arquivos,
    "ler_arquivo": ler_arquivo,
    "criar_arquivo": criar_arquivo,
    "abrir_programa": abrir_programa,
    "abrir_url": abrir_url,
    "mover_mouse": mover_mouse,
    "clicar": clicar,
    "digitar_texto": digitar_texto,
    "pressionar_tecla": pressionar_tecla,
    "tirar_screenshot": tirar_screenshot,
    "posicao_mouse_atual": posicao_mouse_atual,  # <- nova
    "localizar_na_tela": localizar_na_tela,  # <- nova
    "enviar_texto_e_enter": enviar_texto_e_enter,
    "deletar_arquivo": deletar_arquivo,
    "instalar_pacote": instalar_pacote,
    "fechar_janela_ativa": fechar_janela_ativa,
}


def _descrever_acao(nome, args):
    """Monta a descrição detalhada a partir dos argumentos DE VERDADE que
    vão ser usados na execução - não do que a IA disse em texto livre."""
    if nome == "listar_arquivos":
        return f"Listar arquivos da pasta: {args.get('pasta')}."
    if nome == "ler_arquivo":
        return f"Ler o arquivo: {args.get('caminho')}."
    if nome == "abrir_programa":
        return f"⚠️ ABRIR PROGRAMA/ARQUIVO: {args.get('caminho_nome')}."
    if nome == "criar_arquivo":
        caminho = args.get("caminho", "")
        conteudo = args.get("conteudo", "")
        existe = os.path.exists(caminho)
        aviso = "⚠️ VAI SOBRESCREVER um arquivo existente" if existe else "vai criar um arquivo novo"
        return f"⚠️ CRIAR ARQUIVO ({aviso}): {caminho} ({len(conteudo)} caracteres de conteúdo)."
    if nome == "abrir_url":
        return f"abrir o site: {args.get('url')}."
    if nome == "mover_mouse":
        return f"Mover o mouse para ({args.get('x')}, {args.get('y')})."
    if nome == "posicao_mouse_atual":
        return "Verificar a posição atual do mouse"
    if nome == "localizar_na_tela":
        return f"Tirar um screenshot e localizar na tela \"{args.get('descricao_alvo')}\"."
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
    """Ponto de entrada único: a TUI (interface/interface.py, via jarvis.ia.motor) chama só isso.
    Sempre imprime a descrição. Ações enviar/deletar/instalar/fechar
    SEMPRE passam por `confirmar` antes de rodar - não é opcional."""
    if nome not in CATEGORIA_ACAO:
        return f"❌ Ação desconhecida: {nome}"

    funcao = _FUNCOES_ACAO[nome]
    parametros_validos = set(inspect.signature(funcao).parameters.keys())
    argumentos = {k: v for k, v in argumentos.items() if k in parametros_validos}

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
            "name": "listar_arquivos",
            "description": "Lista os arquivos e subpastas dentro de uma pasta. Use isso ANTES de criar um arquivo novo, para conferir o que já existe e evitar duplicar arquivos parecidos com nomes diferentes.",
            "parameters": {
                "type": "object",
                "properties": {"pasta": {"type": "string", "description": "Caminho absoluto da pasta a listar (ex: 'C:\\Users\\monte\\Desktop')."}},
                "required": ["pasta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": (
                "Lê o conteúdo de um arquivo do disco (.pdf, .txt, .md, .html, .py, "
                ".js, .css, .json, .csv). Use isso sempre que o usuário mencionar um "
                "caminho de arquivo na conversa, pedir para você analisar/resumir um "
                "arquivo, ou quando você precisar reler o conteúdo real de um arquivo "
                "que você mesmo criou antes (em vez de confiar apenas na memória da "
                "conversa). Se o tipo de arquivo não for suportado, retorna um erro "
                "claro em vez de inventar conteúdo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho absoluto do arquivo a ler."},
                    "pergunta_busca": {"type": "string", "description": "Só usado para PDFs: o que buscar dentro do documento (ex: 'resumo principal', 'conclusão'). Padrão: resumo geral."},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_arquivo",
            "description": "[REQUER CONFIRMAÇÃO] Cria um arquivo de texto com o conteúdo especificado. Se o arquivo já existir, sobrescreve.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho absoluto do arquivo a criar (ex: 'C:\\Users\\monte\\Desktop\\pagina.html')."},
                    "conteudo": {"type": "string", "description": "Conteúdo de texto a escrever no arquivo."},
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_programa",
            "description": "[REQUER CONFIRMAÇÃO] Abre um programa instalado (por caminho completo do .exe, ou pelo nome se estiver no PATH, ex: 'notepad', 'calc') OU um arquivo com o programa padrão associado à sua extensão (ex: um .html abre no navegador padrão).",
            "parameters": {
                "type": "object",
                "properties": {"caminho_nome": {"type": "string", "description": "Caminho do executável/arquivo ou nome do programa."}},
                "required": ["caminho_nome"],
            },
        },
    },
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
            "name": "posicao_mouse_atual",
            "description": "Retorna a posição X,Y ATUAL do mouse na tela. Use isso para saber onde o mouse está de verdade, em vez de adivinhar.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "localizar_na_tela",
            "description": (
                "Tira um screenshot da tela ATUAL e usa um modelo de visão para tentar "
                "localizar a posição de pixel (x, y) aproximada de um elemento visual "
                "descrito (ex: um botão, um texto, um item de lista, um ícone). "
                "SEMPRE use esta ferramenta ANTES de chamar 'clicar' com coordenadas "
                "específicas quando você não tiver certeza exata de onde o elemento está — "
                "NUNCA invente ou chute coordenadas de pixel sem antes usar esta ferramenta "
                "ou sem o usuário ter fornecido as coordenadas explicitamente. Esta ferramenta "
                "pode retornar 'NAO_ENCONTRADO' se não conseguir localizar o elemento; nesse "
                "caso, informe isso ao usuário em vez de clicar em qualquer lugar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "descricao_alvo": {
                        "type": "string",
                        "description": "Descrição do elemento a localizar na tela (ex: 'botão de play do Spotify', 'campo de busca do navegador').",
                    }
                },
                "required": ["descricao_alvo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_url",
            "description": "Abre uma URL/site no navegador padrão do usuário. Use isso para abrir qualquer site (ex: YouTube, UOL, Google).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL ou domínio do site a abrir."}},
                "required": ["url"],
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
