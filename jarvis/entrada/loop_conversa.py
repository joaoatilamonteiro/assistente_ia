"""
Loop principal de conversa: é aqui que a entrada do usuário (texto,
comandos com \\, arquivos, imagens e prints) é lida, interpretada e
mandada pra IA (nuvem via Groq, com fallback pro Ollama local).
"""
# Imports da biblioteca padrão
import base64
import json
import os
import re
import subprocess
from datetime import datetime

# Imports de terceiros
import PyPDF2

# Imports locais
from jarvis.config import client_local, client, modelo_local, regras_base, prompts_especialistas, carregar_capacidades_ia
from jarvis.utils.animacao import LoadingAnimado
from jarvis.utils.texto import monta_historico_slim, parece_recusa
from jarvis.ia.visao import analisar_imagem
from jarvis.ia.roteador import interpreta_comando, comprime_memoria
from jarvis.ia.ferramentas import ferramentas_jarvis
from jarvis.memoria.embeddings import gerar_embedding, buscar_memoria_semantica, fatiar_e_buscar_documento
from jarvis.memoria.persistencia import carregar_historico, salvar_historico
from jarvis.integracoes.google_calendar import adicionar_multiplos_eventos, apagar_eventos_por_termo, editar_evento_por_termo
from jarvis.integracoes.groq_status import verificar_saude_api
from jarvis.web.renderizador import renderizar_no_navegador
from jarvis.entrada.captura_tela import pega_print


def iniciar_conversa():
    # ==========================================
    # MEMÓRIA E CONFIGURAÇÃO
    # ==========================================
    historico = carregar_historico()

    memoria_curto_p = ""

    modo_ia = "auto"  # auto, local, nuvem

    capacidades_ia = carregar_capacidades_ia()

    repescagem = False

    # ==========================================
    # LOOP PRINCIPAL DE CONVERSA
    # ==========================================
    while True:
        if not repescagem:
            pergunta = input("\nVocê: ").strip()
        else:
            print("🔄 Jarvis: Processando o resgate de memória...")

        if not pergunta:
            continue

        print("#####")

        intencao = {"comando": "normal", "especialidade": "geral"}
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
                memoria_curto_p = ""
                print("esqueci de tudo ja!")
                continue
            elif comando == "help":
                print(
                    "💡 Dica: Digite '\\arquivo' para enviar um documento local.\nDigite '\\sair' para encerrar o chat.\nDigite '\\multi' para inserir múltiplas linhas.\nDigite '\\print' para analisar a ultima print tirada")
                continue

            elif comando.startswith("modo"):
                partes = comando.split()
                alvo = partes[1] if len(partes) > 1 else ""
                descricao = {
                    "auto": "Automatico, enquanto a IA local estiver disponivel ela irá operar, quando nao mais cairá no local",
                    "local": "Local, sempre usa o llm local, nao usa o da nuvem quando essa opcão está ativada\nOBS:por enquanto sem as ferramentas de calendario",
                    "nuvem": "usará apenas a nuvem, maior poder de processamento, integração com calendario, entretanto, tem menos tokens"
                }

                if alvo in descricao:
                    modo_ia = alvo
                    print(f"modo alterado para: {descricao[modo_ia]}")

                else:
                    print(f"modo atual: '{modo_ia}' - {descricao[modo_ia]}")
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
            elif comando == "equacao":
                if len(historico) > 1:
                    ultima_resposta = historico[-1]["content"]
                    renderizar_no_navegador(ultima_resposta)
                else:
                    print("Não ha historico para rendenrizar")
                continue

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

        if not ignora_qwen:
            loading = LoadingAnimado("🧭 Interpretando comando")
            loading.iniciar()
            intencao = interpreta_comando(pergunta)
            loading.parar()

        if intencao.get("comando") == "buscar_memoria":
            print("🤖 Jarvis: Estou vasculhando meus arquivos (Busca Semântica)...")

            loading = LoadingAnimado("🔍 Procurando vetores no passado")
            loading.iniciar()
            memoria_resgatada = buscar_memoria_semantica(pergunta, historico)
            loading.parar()

            if memoria_resgatada:
                print("🧠 Achei memórias conectadas a esse assunto!")

                texto_bruto_para_resumir = ""
                for m in memoria_resgatada:
                    texto_bruto_para_resumir += f"[{m.get('data', '')}] {m.get('role').upper()}: {m.get('content')}\n\n"

                loading = LoadingAnimado("🗜️ Comprimindo memória")
                loading.iniciar()
                contexto_comprimido = comprime_memoria(texto_bruto_para_resumir)
                loading.parar()
                memoria_curto_p = f"--- CONTEXTO RESGATADO ---\n{contexto_comprimido}\n--------------------------"
            else:
                print("📭 Não achei conexões semânticas úteis nos arquivos antigos.")

        if not pergunta:
            continue

        # ==========================================
        # --- ENVIO PARA A IA ---
        # ==========================================
        historico.append({
            "role": "user",
            "content": pergunta,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        })

        # Sua conta Groq tem limite de 8000 tokens/minuto (TPM) por request nesse
        # modelo. O "Requested" da Groq soma: system prompt + histórico + o
        # max_completion_tokens reservado pra resposta. Orçamento apertado aqui
        # (2500 de histórico) pra sobrar espaço de verdade pra resposta sem estourar.
        historico_enxuto = monta_historico_slim(historico, orcamento_token=2500)

        repescagem = True
        while repescagem:
            repescagem = False

            especialidade_identificada = intencao.get("especialidade", "geral")

            prompt_dinamico = regras_base + " " + prompts_especialistas.get(especialidade_identificada,
                                                                            prompts_especialistas["geral"])

            info_api = [{"role": "system", "content": prompt_dinamico}]

            if capacidades_ia:
                info_api.append({"role": "system", "content": capacidades_ia})
            if memoria_curto_p != "":
                info_api.append({
                    "role": "system",
                    "content": f"ATENÇÃO MÁXIMA: O usuário está te perguntando sobre um assunto do passado. AJA COMO SE VOCÊ SE LEMBRASSE DE TUDO DE FORMA NATURAL! NUNCA diga 'como um modelo de IA', 'não tenho memória', ou 'eu não sei' para esta pergunta. Use os dados resgatados abaixo para responder à pergunta atual do usuário:\n\n{memoria_curto_p}"
                })

            for info in historico_enxuto:
                info_api.append({
                    "role": info.get("role", "user"),
                    "content": info.get("content", "")
                })

            loading = LoadingAnimado("Pensando")
            loading.iniciar()
            if modo_ia == "local":
                loading.parar()
                resposta_completa_da_ia = ""
                ferramentas_acionadas = {}

                loading_local = LoadingAnimado("🖥️ Mente local (Ollama) pensando")
                loading_local.iniciar()
                try:
                    # Adicionamos as ferramentas aqui também!
                    completion_local = client_local.chat.completions.create(
                        model=modelo_local,
                        messages=info_api,
                        temperature=0.7,
                        tools=ferramentas_jarvis,
                        tool_choice="auto",
                        stream=True,
                        timeout=60.0,
                    )

                    primeiro_pedaco = True
                    for chunk in completion_local:
                        if not chunk.choices:
                            continue

                        delta = chunk.choices[0].delta

                        # Captura de texto normal via stream
                        if delta.content:
                            if primeiro_pedaco:
                                loading_local.parar()
                                print("IA LOCAL: ", end="")
                                primeiro_pedaco = False
                            pedaco = delta.content
                            resposta_completa_da_ia += pedaco
                            print(pedaco, end="", flush=True)

                        # Captura de chamadas de ferramentas (Function Calling) no Ollama
                        if delta.tool_calls:
                            if primeiro_pedaco:
                                loading_local.parar()
                                primeiro_pedaco = False

                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in ferramentas_acionadas:
                                    ferramentas_acionadas[idx] = {
                                        "id": tc.id,
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments or ""
                                    }
                                else:
                                    if tc.function.arguments:
                                        ferramentas_acionadas[idx]["arguments"] += tc.function.arguments

                    if primeiro_pedaco:
                        loading_local.parar()
                        print("Nenhuma resposta gerada pelo modelo local")
                    print("\n")

                    if ferramentas_acionadas:
                        print("🤖 Jarvis (Local): Entendido! Acionando o calendário...")

                        lista_tool_calls_formatada = []
                        for idx, tc_data in ferramentas_acionadas.items():
                            lista_tool_calls_formatada.append({
                                "id": tc_data["id"],
                                "type": "function",
                                "function": {
                                    "name": tc_data["name"],
                                    "arguments": tc_data["arguments"]
                                }
                            })

                        info_api.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": lista_tool_calls_formatada
                        })

                        for idx, tc_data in ferramentas_acionadas.items():
                            print(f"\n🛠️ [RAIO-X LOCAL] Ferramenta chamada: '{tc_data['name']}'")
                            print(f"🛠️ [RAIO-X LOCAL] Dados enviados: {tc_data['arguments']}\n")

                            if tc_data["name"] == "adicionar_multiplos_eventos":
                                try:
                                    argumentos = json.loads(tc_data["arguments"])
                                    resultado_funcao = adicionar_multiplos_eventos(eventos=argumentos.get("eventos", []))
                                    print(f"\n{resultado_funcao}")
                                except Exception as e:
                                    resultado_funcao = f"Erro na função: {str(e)}"

                            elif tc_data["name"] == "apagar_eventos_por_termo":
                                try:
                                    argumentos = json.loads(tc_data["arguments"])
                                    resultado_funcao = apagar_eventos_por_termo(termo_busca=argumentos.get("termo_busca"))
                                    print(f"\n🗑️ {resultado_funcao}")
                                except Exception as e:
                                    resultado_funcao = f"Erro na função de apagar: {str(e)}"

                            elif tc_data["name"] == "editar_evento_por_termo":
                                try:
                                    argumentos = json.loads(tc_data["arguments"])
                                    resultado_funcao = editar_evento_por_termo(
                                        termo_busca=argumentos.get("termo_busca"),
                                        novo_resumo=argumentos.get("novo_resumo"),
                                        nova_data_hora_inicio=argumentos.get("nova_data_hora_inicio"),
                                        nova_data_hora_fim=argumentos.get("nova_data_hora_fim"),
                                        novo_lembrete_minutos=argumentos.get("novo_lembrete_minutos")
                                    )
                                    print(f"\n{resultado_funcao}")
                                except Exception as e:
                                    resultado_funcao = f"erro na funcao de editar {str(e)}"
                                    print(f"\n{resultado_funcao}")

                            info_api.append({
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "name": tc_data["name"],
                                "content": str(resultado_funcao)
                            })

                        print("🖥️ Jarvis (Local): Recebendo confirmação final...")
                        loading_local_final = LoadingAnimado("🖥️ Processando resposta final local")
                        loading_local_final.iniciar()

                        completion_final_local = client_local.chat.completions.create(
                            model=modelo_local,
                            messages=info_api,
                            temperature=0.7,
                            tools=ferramentas_jarvis,
                            stream=True,
                            timeout=60.0
                        )

                        primeiro_pedaco = True
                        for chunk in completion_final_local:
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            if delta.content:
                                if primeiro_pedaco:
                                    loading_local_final.parar()
                                    print("IA LOCAL: ", end="")
                                    primeiro_pedaco = False
                                print(delta.content, end="", flush=True)
                                resposta_completa_da_ia += delta.content
                        loading_local_final.parar()
                        print("\n")

                except Exception as erro_local:
                    loading_local.parar()
                    print(f"Erro no modo local {erro_local}")
                    historico.pop()
                    continue

            else:
                try:
                    # --- TENTATIVA 1: NUVEM (GROQ) ---
                    completion = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=info_api,
                        temperature=0.7,
                        tools=ferramentas_jarvis,
                        tool_choice="auto",
                        max_completion_tokens=2000,  # sua conta tem TPM 8000; isso deixa espaço pro histórico caber junto
                        top_p=1,
                        stream=True
                    )

                    primeiro_pedaco = True
                    resposta_completa_da_ia = ""
                    tamanho_linha_atual = 0
                    limite_carac = 80
                    ferramentas_acionadas = {}

                    for chunk in completion:
                        if not chunk.choices:
                            continue

                        delta = chunk.choices[0].delta

                        if delta.content:
                            if primeiro_pedaco:
                                loading.parar()
                                print("IA: ", end="")
                                primeiro_pedaco = False

                            texto_recebido = delta.content
                            resposta_completa_da_ia += texto_recebido

                            for letra in texto_recebido:
                                if letra == '\n':
                                    print(letra, end="", flush=True)
                                    tamanho_linha_atual = 0
                                elif tamanho_linha_atual >= limite_carac and letra == ' ':
                                    print("\n", end="", flush=True)
                                    tamanho_linha_atual = 0
                                else:
                                    print(letra, end="", flush=True)
                                    tamanho_linha_atual += 1

                        if delta.tool_calls:
                            if primeiro_pedaco:
                                loading.parar()
                                primeiro_pedaco = False

                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in ferramentas_acionadas:
                                    ferramentas_acionadas[idx] = {
                                        "id": tc.id,
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments or ""
                                    }
                                else:
                                    if tc.function.arguments:
                                        ferramentas_acionadas[idx]["arguments"] += tc.function.arguments

                    print("\n")

                    # --- EXECUÇÃO DE FERRAMENTAS ---
                    if ferramentas_acionadas:
                        print("🤖 Jarvis: Entendido! Acionando o calendário...")

                        lista_tool_calls_formatada = []
                        for idx, tc_data in ferramentas_acionadas.items():
                            lista_tool_calls_formatada.append({
                                "id": tc_data["id"],
                                "type": "function",
                                "function": {
                                    "name": tc_data["name"],
                                    "arguments": tc_data["arguments"]
                                }
                            })

                        info_api.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": lista_tool_calls_formatada
                        })

                        for idx, tc_data in ferramentas_acionadas.items():
                            print(f"\n🛠️ [RAIO-X] Ferramenta chamada pela IA: '{tc_data['name']}'")
                            print(f"🛠️ [RAIO-X] Dados enviados: {tc_data['arguments']}\n")

                            if tc_data["name"] == "adicionar_multiplos_eventos":
                                try:
                                    argumentos = json.loads(tc_data["arguments"])
                                    resultado_funcao = adicionar_multiplos_eventos(eventos=argumentos.get("eventos", []))
                                    print(f"\n{resultado_funcao}")
                                except Exception as e:
                                    resultado_funcao = f"Erro na função: {str(e)}"

                            elif tc_data["name"] == "apagar_eventos_por_termo":
                                try:
                                    argumentos = json.loads(tc_data["arguments"])
                                    resultado_funcao = apagar_eventos_por_termo(termo_busca=argumentos.get("termo_busca"))
                                    print(f"\n🗑️ {resultado_funcao}")
                                except Exception as e:
                                    resultado_funcao = f"Erro na função de apagar: {str(e)}"

                            elif tc_data["name"] == "editar_evento_por_termo":
                                try:
                                    argumentos = json.loads(tc_data["arguments"])
                                    resultado_funcao = editar_evento_por_termo(
                                        termo_busca=argumentos.get("termo_busca"),
                                        novo_resumo=argumentos.get("novo_resumo"),
                                        nova_data_hora_inicio=argumentos.get("nova_data_hora_inicio"),
                                        nova_data_hora_fim=argumentos.get("nova_data_hora_fim"),
                                        novo_lembrete_minutos=argumentos.get("novo_lembrete_minutos")
                                    )
                                    print(f"\n{resultado_funcao}")
                                except Exception as e:
                                    resultado_funcao = f"erro na funcao de editar {str(e)}"
                                    print(f"\n{resultado_funcao}")

                            info_api.append({
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "name": tc_data["name"],
                                "content": str(resultado_funcao)
                            })

                        print("☁️ Jarvis: Recebendo confirmação final...")
                        loading = LoadingAnimado("☁️ Recebendo confirmação final")
                        loading.iniciar()
                        completion_final = client.chat.completions.create(
                            model="openai/gpt-oss-120b",
                            messages=info_api,
                            temperature=0.7,
                            tools=ferramentas_jarvis,
                            max_completion_tokens=2000,
                            stream=True
                        )

                        primeiro_pedaco = True
                        for chunk in completion_final:
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            if delta.content:
                                if primeiro_pedaco:
                                    loading.parar()
                                    print("IA: ", end="")
                                    primeiro_pedaco = False
                                print(delta.content, end="", flush=True)
                                resposta_completa_da_ia += delta.content
                        loading.parar()
                        print("\n")

                # --- TENTATIVA 2: FALLBACK LOCAL (OLLAMA) ---
                except Exception as erro_groq:
                    loading.parar()
                    erro_str = str(erro_groq)
                    if modo_ia == "auto" and ("413" in erro_str or "429" in erro_str):
                        print("\n⚠️ [ALERTA DE INFRAESTRUTURA] Groq sobrecarregada ou limite atingido!")
                        print("🔄 Acionando a Rota de Fuga: Transferindo carga para o Ollama local...")

                        info_api_local = [info_api[0]]

                        if len(info_api) > 1 and "ATENÇÃO MÁXIMA" in info_api[1].get("content", ""):
                            info_api_local.append(info_api[1])

                        for hist in historico_enxuto[-4:]:
                            if hist.get("role") == "assistant" and parece_recusa(hist.get("content", "")):
                                continue
                            info_api_local.append({"role": hist.get("role", "user"), "content": hist.get("content", "")})

                        if info_api_local[-1]["content"] != pergunta:
                            info_api_local.append({"role": "user", "content": pergunta})

                        loading_local = LoadingAnimado("🖥️ Mente local (Ollama) pensando")
                        loading_local.iniciar()
                        try:
                            completion_local = client_local.chat.completions.create(
                                model=modelo_local,
                                messages=info_api_local,
                                temperature=0.7,
                                stream=True,
                                timeout=60.0,
                            )

                            primeiro_pedaco = True
                            resposta_completa_da_ia = ""

                            for chunk in completion_local:
                                if chunk.choices and chunk.choices[0].delta.content:
                                    if primeiro_pedaco:
                                        loading_local.parar()
                                        print("IA (Ollama Local): ", end="")
                                        primeiro_pedaco = False

                                    pedaco = chunk.choices[0].delta.content
                                    resposta_completa_da_ia += pedaco
                                    print(pedaco, end="", flush=True)

                            if primeiro_pedaco:
                                loading_local.parar()
                                print("IA (Ollama Local): [Nenhuma resposta gerada pelo modelo local]")

                            print("\n")
                        except Exception as erro_local:
                            if primeiro_pedaco:
                                loading_local.parar()
                            print(f"\n❌ Falha catastrófica em ambas as mentes. Erro Ollama Local: {erro_local}")
                            historico.pop()
                            continue
                    else:
                        # O bloco else captura qualquer erro que não seja tratado acima
                        print(f"\n❌ ERRO NA NUVEM: {erro_str}")
                        historico.pop()
                        continue

            # --- REPESCAGEM VETORIAL ---
            if (("eu não sei" in resposta_completa_da_ia.lower().strip() or parece_recusa(resposta_completa_da_ia))
                    and memoria_curto_p == ""):
                print("\n🤖 O modelo não achou no contexto curto. Acionando busca vetorial...")

                loading = LoadingAnimado("Buscando memória semântica")
                loading.iniciar()
                memoria_resgatada_repescagem = buscar_memoria_semantica(pergunta, historico)
                loading.parar()

                if memoria_resgatada_repescagem:
                    print("Achei conexões no passado! Resumindo o assunto...\n" + "-" * 40)

                    texto_bruto_para_resumir = ""
                    for m in memoria_resgatada_repescagem:
                        texto_bruto_para_resumir += f"[{m.get('role').upper()}]: {m.get('content')}\n"

                    loading = LoadingAnimado("🗜️ Comprimindo memória resgatada")
                    loading.iniciar()
                    contexto_comprimido = comprime_memoria(texto_bruto_para_resumir)
                    loading.parar()
                    memoria_curto_p = f"--- RESUMO DO CONTEXTO ANTIGO ---\n{contexto_comprimido}\n---------------------------------"
                    repescagem = True
                    continue
                else:
                    print("📭 Realmente não achei conexões semânticas nos arquivos antigos.")

            # --- SALVAMENTO E VETORIZAÇÃO ---
            texto_vetorizar = f"Usuário: {pergunta} | IA: {resposta_completa_da_ia}"

            historico.append({
                "role": "assistant",
                "content": resposta_completa_da_ia,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "embedding": gerar_embedding(texto_vetorizar)
            })

            salvar_historico(historico)
