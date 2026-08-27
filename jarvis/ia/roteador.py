"""Roteador de comandos e compressor de memória.

Usa seu próprio cliente Ollama local (client_roteador_local), separado do
client_local usado no restante do Jarvis (jarvis.config), pra evitar
misturar o modelo de classificação/compressão com o modelo de chat/visão.
"""
import json

from openai import OpenAI

client_roteador_local = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=30.0)

# Mesmo modelo usado na visão (qwen2.5vl:7b) - texto e visão no mesmo modelo.
modelo_roteador_local = "qwen2.5vl:7b"


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
            max_tokens=600
        )
        return resposta.choices[0].message.content.strip()

    except Exception as e:
        print(f"⚠️ Falha ao comprimir memória com o Qwen Local: {e}")
        # Rota de escape: se a IA falhar, nós cortamos o texto na marreta para não crashar o sistema principal!
        return texto_bruto[-1500:]
