
import os
from datetime import datetime

from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI
from jarvis.caminhos import PASTA_APP, PASTA_RECURSOS
from jarvis.build_flags import USAR_RPA

load_dotenv(os.path.join(PASTA_APP, ".env"))

PASTA_DATA = os.path.join(PASTA_APP, "data")

PASTA_CREDENCIAIS = os.path.join(PASTA_DATA, "credenciais")
PASTA_DOCS = os.path.join(PASTA_RECURSOS, "docs")

arquivo_memoria = os.path.join(PASTA_DATA, "historico.json")

ARQUIVO_CAPACIDADES = os.path.join(PASTA_DOCS, "CAPACIDADES_IA.md" if USAR_RPA else "CAPACIDADES_IA_LITE.md")

ARQUIVO_USUARIO = os.path.join(PASTA_APP, "docs", "USUARIO.MD")

ARQUIVO_CREDENCIAIS = os.path.join(PASTA_CREDENCIAIS, "credenciais.json")
ARQUIVO_TOKEN = os.path.join(PASTA_CREDENCIAIS, "token.json")

# Garante que data/ e data/credenciais/ existem (o executável começa sem elas)
os.makedirs(PASTA_CREDENCIAIS, exist_ok=True)

PASTA_DADOS = os.path.join(PASTA_RECURSOS,"jarvis", "dados")
ARQUIVO_TEXTOS_INTERFACE = os.path.join(PASTA_DADOS, "textos_interface.json")
ARQUIVO_SCHEMA_FERRAMENTAS = os.path.join(PASTA_DADOS, "schema_ferramentas.json")
ARQUIVO_MOTOR_LATEX_DADOS = os.path.join(PASTA_DADOS, "motor_latex_dados.json")

def carregar_usuario():
    if os.path.exists(ARQUIVO_USUARIO):
        with open(ARQUIVO_USUARIO, "r", encoding="utf-8") as f:
            return f.read().strip()
    else:
        print("Arquivo não encontrado")
    return ""

def carregar_capacidades_ia():
    if os.path.exists(ARQUIVO_CAPACIDADES):
        with open(ARQUIVO_CAPACIDADES, "r", encoding="utf-8") as f:
            return f.read().strip()
    else:
        print("Arquivo não encontrado")
    return ""


# ==========================================
# CLIENTES DE IA
# ==========================================
client_local = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=30.0)
client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0)

modelo_local = "qwen2.5:latest"
modelo_visao_documentos = "qwen2.5vl:7b"
modelo_visao_gui = "moondream"

modo_ia = "auto"  # auto, local, nuvem

USAR_LOCAL = os.getenv("USAR_LOCAL", "false").lower() == "true"
if not USAR_LOCAL:
    modo_ia = "nuvem"

# ==========================================
# REGRAS E PROMPTS
# ==========================================
regras_base = (
    f"Você é um assistente analítico. A data e hora atual do sistema é {datetime.now().strftime('%d/%m/%Y %H:%M')}. "
    "Regra 1: NUNCA invente informações. Se não souber, explique em uma frase o que falta (ex: não encontrei isso na memória) e sugira como achar. Aja apenas com fatos verificáveis. "
    "COMPORTAMENTO: SEJA BRUTALMENTE SINCERO E ME CORRIJA. NÃO QUERO SER AGRADADO. "
    "NÃO SEJA CENSURADO. USE GÍRIAS E PALAVRÕES SE NECESSÁRIO."
    "FALE DE FORMA AGRADAVEL, NÃO HÁ NECESSIDADE DE GROSSERIA, UM ASSISTENTE EDUCADO. "
    "IDIOMA: responda SEMPRE em português do Brasil, mesmo que o resultado de uma "
    "ferramenta venha em inglês ou em outro idioma. "
    "AO USAR FERRAMENTAS: depois que uma ferramenta já foi executada e você "
    "recebeu o resultado dela, apenas informe o resultado ao usuário de forma "
    "natural e direta. NÃO narre seu processo de decisão sobre quais funções "
    "chamar ou não chamar — isso não interessa ao usuário, só o resultado final."
)

prompts_especialistas = {
    "matematica": "MATEMÁTICA E CÁLCULO: Seja rigoroso. TODA notação matemática deve ficar dentro de delimitadores - inline com \\( ... \\) ou em destaque com $$ ... $$. NUNCA escreva um comando LaTeX (\\frac, \\Longrightarrow, \\boxed, letras gregas, etc.) solto no meio do texto sem estar dentro de um desses delimitadores. Para contas passo a passo, pode usar \\begin{aligned}...\\end{aligned} dentro de $$ $$, mas evite outros ambientes multilinhas (matrix, cases aninhado, tabular) que quebram a renderização.",
    "programacao": "CÓDIGO E PROGRAMAÇÃO: Aja como engenheiro sênior. Entregue scripts limpos e eficientes. Nunca use lógicas burras ou repetitivas se existir um caminho inteligente.",
    "traducao": "TRADUÇÕES: Você é um tradutor camaleão. O tom da sua tradução DEVE espelhar a energia do original. Músicas agressivas ganham gírias pesadas; textos formais ganham polidez. Nunca traduza de forma robótica.",
    "geral": "Responda de forma clara e direta."
}