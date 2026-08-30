import base64
import os
import re
import subprocess
from datetime import datetime

import PyPDF2

# Imports locais
from jarvis.config import client
from jarvis.utils.animacao import LoadingAnimado
from jarvis.utils.tempo import formatar_duracao
from jarvis.ia.visao import analisar_imagem
from jarvis.ia.motor import motor_pensamento
from jarvis.memoria.embeddings import fatiar_e_buscar_documento
from jarvis.integracoes.groq_status import verificar_saude_api
from jarvis.entrada.captura_tela import pega_print


def _callback_cli(tipo, **dados):
    if tipo == "buscando_memoria":
        print("🤖 Jarvis: Estou vasculhando meus arquivos (Busca Semântica)...")
    elif tipo == "memoria_encontrada":
        print("🧠 Achei memórias conectadas a esse assunto!")
    elif tipo == "memoria_nao_encontrada":
        print("📭 Não achei conexões semânticas úteis nos arquivos antigos.")
    elif tipo == "pensando":
        destino = "nuvem (Groq)" if dados.get("destino") == "nuvem" else "local (Ollama)"
        print(f"IA [{destino}]: ", end="")
    elif tipo == "fallback_local":
        print("\n⚠️ [ALERTA DE INFRAESTRUTURA] Groq sobrecarregada ou limite atingido!")
        print("🔄 Acionando a Rota de Fuga: Transferindo carga para o Ollama local...")
    elif tipo == "erro_nuvem":
        print(f"\n❌ ERRO NA NUVEM: {dados.get('erro')}")
    elif tipo == "erro_local":
        print(f"\n❌ Falha catastrófica em ambas as mentes: {dados.get('erro')}")
    elif tipo == "acionando_ferramentas":
        print(f"\n🤖 Jarvis: Entendido! Acionando: {', '.join(dados.get('ferramentas', []))}")
    elif tipo == "ferramenta_executada":
        print(f"🛠️ [RAIO-X] '{dados.get('nome')}' -> {dados.get('resultado')}")
    elif tipo == "recebendo_confirmacao_final":
        print("☁️ Jarvis: Recebendo confirmação final...")
    elif tipo == "repescagem_iniciada":
        print("\n🤖 O modelo não achou no contexto curto. Acionando busca vetorial...")
    elif tipo == "repescagem_encontrada":
        print("Achei conexões no passado! Resumindo o assunto...\n" + "-" * 40)
    elif tipo == "repescagem_vazia":
        print("📭 Realmente não achei conexões semânticas nos arquivos antigos.")
    elif tipo == "resposta_pronta":
        print(f"\n⏱️ Tempo de resposta: {formatar_duracao(dados.get('duracao', 0))}")



def iniciar_conversa():
    motor = motor_pensamento(
        on_evento=_callback_cli,
        on_texto=lambda pedaco: print(pedaco, end="", flush=True),
    )

    # ==========================================
    # LOOP PRINCIPAL DE CONVERSA
    # ==========================================
    while True:
        pergunta = input("\nVocê: ").strip()

        if not pergunta:
            continue

        print("#####")

        ignora_qwen = False

        if pergunta.startswith("\\"):
            comando = pergunta[1:].lower().strip()

            if not comando:
                print("❌ Comando inválido: você digitou apenas a barra.")
                continue
            elif comando == "sair":
                print("Até logo!")
                break
            elif comando == "esquece":
                motor.esquecer_memoria_curta()
                print("esqueci de tudo ja!")
                continue
            elif comando == "help":
                print(
                    "💡 Dica: Digite '\\arquivo' para enviar um documento local.\n"
                    "Digite '\\sair' para encerrar o chat.\n"
                    "Digite '\\multi' para inserir múltiplas linhas.\n"
                    "Digite '\\print' para analisar a ultima print tirada.\n"
                    "(equações agora já aparecem em unicode direto na tela - não precisa mais de '\\equacao')")
                continue

            elif comando.startswith("modo"):
                partes = comando.split()
                alvo = partes[1] if len(partes) > 1 else ""
                descricao = {
                    "auto": "Automatico, enquanto a IA local estiver disponivel ela irá operar, quando nao mais cairá no local",
                    "local": "Local, sempre usa o llm local, nao usa o da nuvem quando essa opcão está ativada\nOBS:por enquanto sem as ferramentas de calendario",
                    "nuvem": "usará apenas a nuvem, maior poder de processamento, integração com calendario, entretanto, tem menos tokens"
                }

                if motor.definir_modo(alvo):
                    print(f"modo alterado para: {descricao[motor.modo_ia]}")
                else:
                    print(f"modo atual: '{motor.modo_ia}' - {descricao[motor.modo_ia]}")
                    print("use '\\modo auto'\n'\\modo local'\nmodo nuvem'")
                continue

            elif comando == "multi":
                print("📝 [Modo Multilinha ativado! Cole seu texto. Digite '\\fim' em uma linha vazia para enviar]")
                linhas = []
                while True:
                    linha = input()
                    if linha.strip().lower() == "\\fim":
                        break
                    linhas.append(linha)
                pergunta = "\n".join(linhas)

                if not pergunta:
                    print("Nenhum texto inserido, tente novamente")
                    continue

                print("✅ [Texto capturado. Enviando...]\n")
            elif comando == "saude":
                print("🩺 Verificando os sinais vitais do servidor da Groq...")
                loading = LoadingAnimado("🩺 Consultando a Groq")
                loading.iniciar()
                relatorio_saude = verificar_saude_api(client)
                loading.parar()
                print(f"\n{relatorio_saude}\n")
                continue

            elif comando == "arquivo":
                caminho_arquivo_dito = input("Qual o caminho absoluto do arquivo? ").strip().strip('"').strip("'")
                extensao = os.path.splitext(caminho_arquivo_dito)[1].lower()

                try:
                    leitura_arquivo = ""
                    usar_rag = False

                    if extensao == ".pdf":
                        with open(caminho_arquivo_dito, "rb") as arquivo:
                            leitor_pdf = PyPDF2.PdfReader(arquivo)
                            for pagina in leitor_pdf.pages:
                                texto_pagina = pagina.extract_text()
                                if texto_pagina:
                                    leitura_arquivo += texto_pagina + "\n"
                        usar_rag = True

                    elif extensao in [".png", ".jpg", ".jpeg", ".webp"]:
                        with open(caminho_arquivo_dito, "rb") as img_file:
                            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

                        conteudo_imagem, origem_imagem = analisar_imagem(caminho_arquivo_dito, extensao, img_base64)

                        if origem_imagem == "erro":
                            print(f"❌ {conteudo_imagem}")
                            continue

                        fonte_texto = "sensores locais (Ollama)" if origem_imagem == "local" else "visão na nuvem (Groq)"
                        pergunta = (f"Aqui está a transcrição exata de uma imagem lida pelos {fonte_texto}:\n\n"
                                    f"--- INÍCIO DA IMAGEM ---\n{conteudo_imagem}\n--- FIM DA IMAGEM ---\n\n"
                                    "Por favor, analise esse conteúdo e me pergunte como deseja prosseguir.")

                    elif extensao == ".xopp":
                        # Salva na pasta do projeto (não mais na temp do sistema) pra você
                        # poder abrir e conferir exatamente a imagem que foi mandada pra visão.
                        pasta_debug = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capturas_xournal")
                        os.makedirs(pasta_debug, exist_ok=True)

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        prefixo = f"xopp_{timestamp}"
                        caminho_png_base = os.path.join(pasta_debug, prefixo + ".png")

                        loading = LoadingAnimado("Renderizando tinta do Xournal++")
                        loading.iniciar()

                        try:
                            subprocess.run([r"C:\Program Files\Xournal++\bin\xournalpp.exe", caminho_arquivo_dito, "-i",
                                            caminho_png_base], check=True,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                        except FileNotFoundError:
                            loading.parar()
                            print("o python não achou o xournal app")
                            continue
                        except subprocess.TimeoutExpired:
                            loading.parar()
                            print("❌ O Xournal++ demorou demais pra exportar (travou?). Abortando.")
                            continue

                        # O Xournal++ nomeia páginas extras como "prefixo-1.png", "prefixo-2.png"...
                        # (ou só "prefixo.png" se for documento de 1 página só). Ordena numericamente
                        # (não alfabeticamente) pra não bagunçar a ordem em docs com 10+ páginas.
                        def _numero_da_pagina(nome_arquivo):
                            m = re.search(r'-(\d+)\.png$', nome_arquivo)
                            return int(m.group(1)) if m else 0

                        arquivos_gerados = sorted(
                            (f for f in os.listdir(pasta_debug) if f.startswith(prefixo) and f.endswith(".png")),
                            key=_numero_da_pagina
                        )
                        loading.parar()

                        if not arquivos_gerados:
                            print("❌ ERRO: O Xournal++ rodou, mas falhou ao gerar a imagem.")
                            continue

                        print(f"📄 {len(arquivos_gerados)} página(s) exportada(s) e salvas em: {pasta_debug}")

                        # --- Lê TODAS as páginas (antes só lia a primeira) ---
                        conteudo_por_pagina = []
                        houve_falha_em_alguma_pagina = False

                        for i, nome_arquivo in enumerate(arquivos_gerados, start=1):
                            caminho_pagina = os.path.join(pasta_debug, nome_arquivo)
                            print(f"👁️ Lendo página {i}/{len(arquivos_gerados)}: {nome_arquivo}")

                            with open(caminho_pagina, "rb") as img_file:
                                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

                            conteudo_pagina, origem_pagina = analisar_imagem(caminho_pagina, ".png", img_base64)

                            if origem_pagina == "erro":
                                print(f"⚠️ Falha ao ler a página {i}: {conteudo_pagina}")
                                houve_falha_em_alguma_pagina = True
                                continue

                            conteudo_por_pagina.append(f"--- Página {i} ---\n{conteudo_pagina}")

                        if not conteudo_por_pagina:
                            print("❌ Nenhuma página pôde ser lida (todas falharam).")
                            continue

                        conteudo_imagem = "\n\n".join(conteudo_por_pagina)

                        print("✅ O que eu consegui ler das anotações:")
                        print("-" * 30 + f"\n{conteudo_imagem}\n" + "-" * 30)
                        if houve_falha_em_alguma_pagina:
                            print("⚠️ Atenção: pelo menos uma página falhou na leitura (veja os avisos acima).")

                        pergunta = (f"Acabei de te enviar minhas anotações manuscritas do Xournal++ "
                                    f"({len(arquivos_gerados)} página(s)).\n\n"
                                    f"--- INÍCIO DAS ANOTAÇÕES ---\n{conteudo_imagem}\n--- FIM DAS ANOTAÇÕES ---\n\n"
                                    "Por favor, leia e me diga um breve resumo de qual assunto eu estava escrevendo na mesa digitalizadora.")

                    else:
                        with open(caminho_arquivo_dito, "r", encoding="utf-8") as arquivo:
                            leitura_arquivo = arquivo.read()
                        usar_rag = True

                    if usar_rag:
                        print(f"✅ Arquivo {extensao} carregado na memória. Tamanho: {len(leitura_arquivo)} caracteres.")
                        pergunta_doc = input("\nO que você quer buscar ou saber sobre este documento?\nVocê: ").strip()

                        loading = LoadingAnimado("🔍 Fatiando e vetorizando o documento")
                        loading.iniciar()
                        trechos_relevantes = fatiar_e_buscar_documento(leitura_arquivo, pergunta_doc, top_k=3)
                        loading.parar()

                        pergunta = (f"O usuário enviou o arquivo '{caminho_arquivo_dito}'.\n"
                                    f"Pedido do usuário: {pergunta_doc}\n\n"
                                    f"Responda ESTRITAMENTE com base nestes trechos relevantes extraídos do documento:\n"
                                    f"--- INÍCIO DOS TRECHOS ---\n{trechos_relevantes}\n--- FIM DOS TRECHOS ---\n\n"
                                    "Se a resposta não estiver nos trechos acima, diga 'Essa informação não consta no documento lido'.")

                        print("✅ [Busca vetorial concluída! Néctar da informação enviado para a Mente Principal!]\n")

                except Exception as e:
                    print(f"❌ Erro ao tentar ler o arquivo: {e}")
                    continue
                ignora_qwen = True

            elif comando == "print":
                imagem_endereco = pega_print()
                if imagem_endereco is None:
                    print("a pasta de prints ta vazia")
                else:
                    try:
                        extensao = os.path.splitext(imagem_endereco)[1].lower()

                        with open(imagem_endereco, "rb") as img_file:
                            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        conteudo_imagem, origem_imagem = analisar_imagem(imagem_endereco, extensao, img_base64)

                        if origem_imagem == "erro":
                            print(f"{conteudo_imagem}")
                        else:
                            fonte_texto = "sensores locais (Ollama)" if origem_imagem == "local" else "visão na nuvem (Groq)"
                            pergunta = (f"Aqui está a transcrição exata de uma imagem lida pelos {fonte_texto}:\n\n"
                                        f"--- INÍCIO DA IMAGEM ---\n{conteudo_imagem}\n--- FIM DA IMAGEM ---\n\n"
                                        "Por favor, analise esse conteúdo e me pergunte como deseja prosseguir.")
                    except Exception as e:
                        print(f"❌ Erro ao processar a print: {e}")

            else:
                print("comando não achado")
                continue


        if not pergunta:
            continue

        loading = LoadingAnimado("Pensando")
        loading.iniciar()
        try:
            resultado = motor.processar(pergunta, ignora_intencao=ignora_qwen)
        except Exception as erro:
            loading.parar()
            print(f"\n❌ Não deu pra responder dessa vez: {erro}")
            continue
        loading.parar()

        print(f"\nJarvis: {resultado['resposta_formatada']}\n")