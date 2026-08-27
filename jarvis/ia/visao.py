"""Leitura óptica de imagens: tenta primeiro localmente via Ollama,
com fallback para a nuvem (Groq) se a leitura local falhar ou vier corrompida."""
import mimetypes

from jarvis.config import client_local, client, modelo_visao_local
from jarvis.utils.animacao import LoadingAnimado
from jarvis.utils.texto import verifica_qualidade_resposta


def analisar_imagem(caminho_arquivo, extensao, img_base64):
    mime_tipo = mimetypes.guess_type(f"arquivo{extensao}")[0] or "image/jpeg"
    data_url = f"data:{mime_tipo};base64,{img_base64}"
    prompt_visao = (
        "Você é um leitor óptico. Transcreva TODO o texto desta imagem. "
        "Se houver matemática, escreva rigorosamente em LaTeX. Apenas transcreva o que vê."
    )

    conteudo_imagem = None

    # --- TENTATIVA 1: Local (Ollama) ---
    loading = LoadingAnimado("👁️ Ollama local analisando a imagem")
    loading.iniciar()
    try:
        resposta_visao = client_local.chat.completions.create(
            model=modelo_visao_local,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_visao},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=2048,
            timeout=90.0,  # visão local demora mais que texto, dá mais fôlego antes de desistir
        )
        conteudo_imagem = resposta_visao.choices[0].message.content
    except Exception as erro_local_visao:
        loading.parar()
        print(f"⚠️ Falha na visão local (Ollama), erro: {erro_local_visao}\n🔄 Acionando fallback pra nuvem...")
        conteudo_imagem = None
    else:
        loading.parar()
        if verifica_qualidade_resposta(conteudo_imagem):
            print(
                "⚠️ A visão local (Ollama) não aguentou e devolveu uma resposta corrompida.\n🔄 Acionando fallback pra nuvem...")
            conteudo_imagem = None
        else:
            print("✅ Imagem lida localmente via Ollama!")
            return conteudo_imagem, "local"

    # --- TENTATIVA 2: Nuvem (Groq - qwen/qwen3.6-27b) ---
    loading = LoadingAnimado("☁️ Analisando imagem na nuvem")
    loading.iniciar()
    try:
        resposta_visao_cloud = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_visao},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ],
            temperature=0.1,
            max_completion_tokens=2048,
        )
        conteudo_imagem = resposta_visao_cloud.choices[0].message.content
        loading.parar()
        print("✅ [Imagem lida na nuvem (Groq) com sucesso!]\n")
        return conteudo_imagem, "nuvem"

    except Exception as erro_cloud_visao:
        loading.parar()
        return f"não foi possivel interpretar a imagem nem na nuvem e nem localmente via Ollama\nErro:{erro_cloud_visao}", "erro"
