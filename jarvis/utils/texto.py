

def estimar_tokens(texto):
    return max(1, len(texto or "") // 4)


def monta_historico_slim(historico, orcamento_token=6000, min_msg=4):
    if len(historico) <= min_msg:
        return historico

    base = historico[:2]
    tokens_base = sum(estimar_tokens(m.get("content", "")) for m in base)

    selecionados_proxs = []
    tokens_usados = tokens_base

    for msg in reversed(historico[2:]):
        custo = estimar_tokens(msg.get("content", ""))

        if tokens_usados + custo > orcamento_token and len(selecionados_proxs) >= min_msg:
            break

        selecionados_proxs.append(msg)
        tokens_usados += custo

    selecionados_proxs.reverse()
    return base + selecionados_proxs


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
