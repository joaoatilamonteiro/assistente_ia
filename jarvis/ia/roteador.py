
import json

from openai import OpenAI

client_roteador_local = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=30.0)

# Mesmo modelo usado na visão (qwen2.5vl:7b) - texto e visão no mesmo modelo.
modelo_roteador_local = "qwen2.5vl:7b"

# ==========================================
# CLASSIFICAÇÃO RÁPIDA (SEM IA) - CUSTO ~0ms
# ==========================================
# interpreta_comando (mais abaixo) chama um modelo local de 7B só pra
# classificar a frase - em CPU isso custa segundos por mensagem. A imensa
# maioria das mensagens do dia a dia dá pra classificar por palavra-chave,
# instantaneamente. Só cai no modelo de IA quando a heurística fica em dúvida.
_PALAVRAS_BUSCAR_MEMORIA = [
    "lembra", "lembrar", "lembrou", "resgata", "resgatar", "resgate",
    "relembra", "relembrar", "antes", "anteriormente", "passado",
    "primeira mensagem", "primeiro assunto", "continuando", "continua de onde",
    "voltando naquele assunto", "já te falei", "ja te falei", "conversamos sobre",
]

_PALAVRAS_MATEMATICA = [
    "equação", "equacao", "calcul", "deriv", "integral", "matemática", "matematica",
    "álgebra", "algebra", "geometria", "trigonometria", "logaritmo",
]

_PALAVRAS_PROGRAMACAO = [
    "código", "codigo", "python", "javascript", "typescript", "função", "funcao",
    "bug", "compila", "programa", "script", " api ", "loop", "variável", "variavel",
    "biblioteca", "framework", "sql", "git",
]

_PALAVRAS_TRADUCAO = [
    "traduz", "traducao", "tradução", "translate", "em inglês", "em ingles",
    "para o inglês", "para o ingles", "para o espanhol", "para o francês",
]

# Mensagens muito curtas (saudação, confirmação, small talk) quase nunca
# precisam de classificação por IA - a partir desse nº de palavras a heurística
# desiste e deixa o modelo local decidir.
_LIMITE_PALAVRAS_MENSAGEM_CURTA = 12


def _contem_alguma(frase_lower, palavras):
    return any(p in frase_lower for p in palavras)


def classificar_rapido(frase_usuario):
    """Tenta classificar a frase sem chamar nenhum modelo de IA.

    Retorna o dicionário de intenção se conseguir decidir com confiança,
    ou None se a frase for ambígua/longa e precisar mesmo do roteador via IA.
    """
    frase_lower = frase_usuario.lower()

    if _contem_alguma(frase_lower, _PALAVRAS_BUSCAR_MEMORIA):
        return {"comando": "buscar_memoria", "especialidade": "geral"}

    if _contem_alguma(frase_lower, _PALAVRAS_MATEMATICA):
        return {"comando": "normal", "especialidade": "matematica"}
    if _contem_alguma(frase_lower, _PALAVRAS_PROGRAMACAO):
        return {"comando": "normal", "especialidade": "programacao"}
    if _contem_alguma(frase_lower, _PALAVRAS_TRADUCAO):
        return {"comando": "normal", "especialidade": "traducao"}

    if len(frase_lower.split()) <= _LIMITE_PALAVRAS_MENSAGEM_CURTA:
        return {"comando": "normal", "especialidade": "geral"}

    return None  # ambíguo/longa demais - só aqui vale a pena chamar o modelo local


def interpreta_comando_rapido(frase_usuario):
    """Ponto de entrada usado pelo loop de conversa: tenta a heurística
    instantânea primeiro e só aciona interpreta_comando (IA local) quando
    ela não tem certeza."""
    resultado_heuristico = classificar_rapido(frase_usuario)
    if resultado_heuristico is not None:
        return resultado_heuristico
    return interpreta_comando(frase_usuario)


def interpreta_comando(frase_usuario):
    prompt_sistema = """Você é um roteador de comandos e classificador de contexto de um sistema automatizado. 
            Sua única função é ler a frase do usuário e retornar APENAS um JSON válido. Não diga 'Olá', não explique nada.

            HOJE É: {hoje}.

            REGRA VITAL DE CONTEXTO: Se o usuário pedir algo genérico como 'questão 3', 'a próxima', ou 'traduz o resto', NUNCA extraia palavras genéricas (como 'questão', 'resto', 'próxima') para a chave "contexto". Você DEVE deduzir e retornar o NOME DO ASSUNTO REAL (ex: 'lista', 'modelos', 'arquivo', 'pdf').

            As categorias de "comando" possíveis são:
            1. "buscar_memoria": Usado EXCLUSIVAMENTE quando o usuário pedir para lembrar, resgatar ou continuar um assunto do passado.
            2. "normal": Usado para TODAS as outras frases.

            As categorias de "especialidade" possíveis são (ESCOLHA APENAS UMA): "matematica", "programacao", "traducao", "geral".

            Exemplo 1: "Me diz o enunciado da questão 3." 
            Retorno: {"comando": "buscar_memoria", "contexto": "lista", "especialidade": "matematica"}

            Exemplo 2: "Traduza esse e-mail de trabalho para o inglês."
            Retorno: {"comando": "normal", "especialidade": "traducao"}

        Exemplo 3: "Como faço um loop while em Python?"
        Retorno: {"comando": "normal", "especialidade": "programacao"}

        Exemplo 4: "Ligue as luzes da sala."
        Retorno: {"comando": "normal", "especialidade": "geral"}
        """

    try:
        resposta_local = client_roteador_local.chat.completions.create(
            model=modelo_roteador_local,  # Nome atualizado para o Qwen
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": frase_usuario}
            ],
            temperature=0.1
        )

        tex_json = resposta_local.choices[0].message.content

        # 1. Criamos a variável limpa apenas tirando os espaços em branco das pontas
        tex_json_limpo = tex_json.strip()

        # 2. Se o modelo tentar formatar com markdown (ex: ```json ... ```), nós arrancamos isso
        if "```json" in tex_json_limpo:
            tex_json_limpo = tex_json_limpo.split("```json")[1].split("```")[0].strip()
        elif "```" in tex_json_limpo:
            tex_json_limpo = tex_json_limpo.split("```")[1].split("```")[0].strip()

        return json.loads(tex_json_limpo)

    except Exception as e:
        print(f"⚠️ Erro no agente local: {e}")
        return {"comando": "normal"}  # Rota de escape segura em caso de falha


def comprime_memoria(texto_bruto):
    """Resume um histórico longo de conversas para economizar tokens."""
    if not texto_bruto.strip():
        return ""

    limite_caracteres = 800
    if len(texto_bruto) <= limite_caracteres:
        return texto_bruto.strip()

    prompt_sistema = (
        "Você é um compactador de informações. Leia o histórico de conversa abaixo e faça um resumo ultra conciso "
        "(máximo 2 ou 3 parágrafos) focando APENAS nos fatos, nas dúvidas do usuário, nas resoluções e nos dados técnicos. "
        "Remova saudações, enrolações e conversas fiadas."
    )

    try:
        print("🗜️ Espremendo os dados antigos...")
        # Usando o client local (Qwen) já definido neste arquivo
        resposta = client_roteador_local.chat.completions.create(
            model=modelo_roteador_local,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"HISTÓRICO:\n{texto_bruto}"}
            ],
            temperature=0.3,  # Baixa temperatura para ele não inventar nada
            max_tokens=350
        )
        return resposta.choices[0].message.content.strip()

    except Exception as e:
        print(f"⚠️ Falha ao comprimir memória com o Qwen Local: {e}")
        # Rota de escape: se a IA falhar, nós cortamos o texto na marreta para não crashar o sistema principal!
        return texto_bruto[-1500:]
