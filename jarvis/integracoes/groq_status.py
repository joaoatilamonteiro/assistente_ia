"""Verificação de saúde/limites da API da Groq."""


def verificar_saude_api(client_groq):
    """Faz um ping de 1 token na Groq para extrair os cabeçalhos de Rate Limit (Limites da API)."""
    try:
        # Fazemos uma requisição quase "vazia" e pedimos a raw_response para ler os cabeçalhos ocultos
        resposta_bruta = client_groq.chat.completions.with_raw_response.create(
            model="openai/gpt-oss-120b",  # Usamos o menor modelo possível para não gastar sua cota principal
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1
        )

        headers = resposta_bruta.headers

        # Extrai os limites enviados pelo servidor da Groq
        tokens_minuto = headers.get('x-ratelimit-remaining-tokens', 'Desconhecido')
        req_diarias = headers.get('x-ratelimit-remaining-requests', 'Desconhecido')
        reset_tokens = headers.get('x-ratelimit-reset-tokens', 'Desconhecido')
        reset_req = headers.get('x-ratelimit-reset-requests', 'Desconhecido')

        relatorio = (
            f"🏥 --- SAÚDE DA API (GROQ) ---\n"
            f"🔹 Requisições restantes: {req_diarias} (Reseta em: {reset_req})\n"
            f"🔹 Tokens restantes (Minuto): {tokens_minuto} (Reseta em: {reset_tokens})\n"
            f"------------------------------"
        )
        return relatorio

    except Exception as e:
        return f"❌ Erro ao verificar a saúde da API: {str(e)}"
