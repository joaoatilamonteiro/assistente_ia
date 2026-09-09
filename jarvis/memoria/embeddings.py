
import numpy as np
from sentence_transformers import SentenceTransformer
import os
base_dir = os.getcwd()
caminho_modelo = os.path.join(base_dir,"jarvis", "memoria", "modelo_memoria")
try:
    modelo_embedding = SentenceTransformer(caminho_modelo)
    print("modelo carregado localmente com sucesso")
except Exception as e:
    print(f"não foi possivel carregar o modelo local\nerro{e}")
    try:
        modelo_embedding = SentenceTransformer("all-MiniLM-L6-v2")
        modelo_embedding.save(caminho_modelo)
        print("Modelo salvo com sucesso")
    except Exception as e_download:
        print(f"Erro ao baixar e salvar o modelo\nerro:{e}")

def gerar_embedding(texto):
    return modelo_embedding.encode(texto).tolist()


def cos_sim(a, b):
    if not a or not b:
        return 0
    a_np, b_np = np.array(a), np.array(b)
    return np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np))


def buscar_memoria_semantica(pergunta, historico, top_k=3):

    mensagens_com_vetor = [msg for msg in historico if msg.get("embedding")]
    if not mensagens_com_vetor:
        return []

    vetor_pergunta = np.array(gerar_embedding(pergunta))
    matriz_vetores = np.array([msg["embedding"] for msg in mensagens_com_vetor])

    normas = np.linalg.norm(matriz_vetores, axis=1) * np.linalg.norm(vetor_pergunta)
    normas[normas == 0] = 1e-10  # evita divisão por zero em vetores nulos
    similaridades = (matriz_vetores @ vetor_pergunta) / normas

    # Já ordenado do mais relevante pro menos relevante
    indices_ordenados = np.argsort(similaridades)[::-1]

    resultados = []
    for idx in indices_ordenados:
        # Só pega o que tiver pelo menos 25% de relevância semântica
        if similaridades[idx] <= 0.25:
            break  # como já está ordenado, dá pra parar assim que cair abaixo do limiar
        resultados.append(mensagens_com_vetor[idx])
        if len(resultados) >= top_k:
            break

    return resultados


def fatiar_e_buscar_documento(texto_gigante, pergunta_usuario, top_k=3):

    # 1. Chunking: Pica o texto em pedaços de 1500 caracteres (aprox. 400 tokens)
    tamanho_pedaco = 1500
    pedacos = [texto_gigante[i:i + tamanho_pedaco] for i in range(0, len(texto_gigante), tamanho_pedaco)]

    print(f"✂️ Documento dividido em {len(pedacos)} pedaços. Vetorizando...")

    # 2. Gera o vetor da pergunta
    vetor_pergunta = np.array(gerar_embedding(pergunta_usuario))

    # 3. Vetoriza TODOS os pedaços de uma vez (batch) em vez de um a um -
    # o modelo de embedding processa lotes muito mais rápido que chamadas soltas
    matriz_pedacos = np.array(modelo_embedding.encode(pedacos))

    normas = np.linalg.norm(matriz_pedacos, axis=1) * np.linalg.norm(vetor_pergunta)
    normas[normas == 0] = 1e-10
    similaridades = (matriz_pedacos @ vetor_pergunta) / normas

    # 4. Pega só os pedaços que mais batem com a pergunta
    indices_ordenados = np.argsort(similaridades)[::-1][:top_k]
    melhores_pedacos = [pedacos[i] for i in indices_ordenados]

    # 5. Costura os melhores pedaços juntos
    texto_filtrado = "\n\n...[Corte]...\n\n".join(melhores_pedacos)
    return texto_filtrado
