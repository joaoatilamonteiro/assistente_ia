"""Geração de embeddings e busca semântica na memória (histórico) e em
documentos fatiados (RAG simples)."""
import numpy as np
from sentence_transformers import SentenceTransformer

modelo_embedding = SentenceTransformer("all-MiniLM-L6-v2")


def gerar_embedding(texto):
    return modelo_embedding.encode(texto).tolist()


def cos_sim(a, b):
    if not a or not b:
        return 0
    a_np, b_np = np.array(a), np.array(b)
    return np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np))


def buscar_memoria_semantica(pergunta, historico, top_k=3):
    """Varre o JSON caçando as memórias com maior ligação semântica."""
    vetor_pergunta = gerar_embedding(pergunta)

    resultados = []
    for msg in historico:
        vetor_msg = msg.get("embedding")
        if not vetor_msg:
            continue  # Pula memórias velhas que não têm vetor

        similaridade = cos_sim(vetor_pergunta, vetor_msg)

        # Só pega o que tiver pelo menos 25% de relevância semântica
        if similaridade > 0.25:
            resultados.append((similaridade, msg))
    # Ordena do mais relevante para o menos relevante
    resultados.sort(key=lambda x: x[0], reverse=True)

    # Retorna apenas as mensagens dos Top K resultados
    return [res[1] for res in resultados[:top_k]]


def fatiar_e_buscar_documento(texto_gigante, pergunta_usuario, top_k=3):
    """Fatia um texto gigante, converte em vetores na hora e acha a agulha no palheiro."""

    # 1. Chunking: Pica o texto em pedaços de 1500 caracteres (aprox. 400 tokens)
    tamanho_pedaco = 1500
    pedacos = [texto_gigante[i:i + tamanho_pedaco] for i in range(0, len(texto_gigante), tamanho_pedaco)]

    print(f"✂️ Documento dividido em {len(pedacos)} pedaços. Vetorizando...")

    # 2. Gera o vetor da pergunta
    vetor_pergunta = gerar_embedding(pergunta_usuario)

    # 3. Busca Bruta: Compara a pergunta com CADA pedaço do texto
    resultados = []
    for pedaco in pedacos:
        vetor_pedaco = gerar_embedding(pedaco)
        similaridade = cos_sim(vetor_pergunta, vetor_pedaco)
        resultados.append((similaridade, pedaco))

    # 4. Pega só os pedaços que mais batem com a pergunta
    resultados.sort(key=lambda x: x[0], reverse=True)
    melhores_pedacos = [res[1] for res in resultados[:top_k]]

    # 5. Costura os melhores pedaços juntos
    texto_filtrado = "\n\n...[Corte]...\n\n".join(melhores_pedacos)
    return texto_filtrado
