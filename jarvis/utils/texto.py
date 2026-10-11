

def estimar_tokens(texto):
    return max(1, len(texto or "") // 4)


def monta_historico_slim(historico, orcamento_token=1500, min_msg=2, max_chars_msg=1200):
    selecionadas = []
    usados = 0
    for i, msg in enumerate(reversed(historico)):
        conteudo = msg.get("content", "") or ""
        # só corta mensagens antigas; a pergunta atual (i == 0) vai inteira
        if i > 0 and len(conteudo) > max_chars_msg:
            conteudo = conteudo[:max_chars_msg] + " [...cortado]"
            msg = {**msg, "content": conteudo}
        custo = estimar_tokens(conteudo)
        if usados + custo > orcamento_token and len(selecionadas) >= min_msg:
            break
        selecionadas.append(msg)
        usados += custo
    selecionadas.reverse()
    return selecionadas

def verifica_qualidade_resposta(texto):
    if not texto or len(texto.strip()) < 3:
        return True

    texto_limpo = texto.strip()
    caract_unicos = len(set(texto_limpo))

    if len(texto_limpo) > 20 and caract_unicos <= 3:
        return True

    caractere_comum = max(set(texto_limpo), key=texto_limpo.count)
    proporcao = texto_limpo.count(caractere_comum) / len(texto_limpo)

    if proporcao > 0.5 and len(texto_limpo) > 15:
        return True

    return False


def parece_recusa(texto):
    if not texto:
        return False
    marcadores = [
        "não tenho a capacidade", "não tenho capacidade", "não tenho acesso",
        "não tenho memória", "como um modelo de ia", "como assistente de ia",
        "não consigo acessar", "sou um assistente de inteligência artificial",
        "não tenho a habilidade",
    ]
    texto_lower = texto.lower()
    return any(marcador in texto_lower for marcador in marcadores)
