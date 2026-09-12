from jarvis.config import client

def pesquisa_web(pergunta):
    try:
        resposta = client.chat.completions.create(
            model="groq/compound-mini",
            messages=[{"role": "user", "content": pergunta}],
            compound_custom={"tools": {"enabled_tools": ["web_search"]}},
        )
        conteudo = resposta.choices[0].message.content

        # Opcional: incluir quais fontes foram usadas
        ferramentas_usadas = getattr(resposta.choices[0].message, "executed_tools", None)
        return conteudo
    except Exception as e:
        return f"Não consegui pesquisar na internet agora: {e}"