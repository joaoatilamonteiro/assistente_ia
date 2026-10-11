import json
import time
from datetime import datetime
import threading
from jarvis.config import (
    client_local, client, modelo_local, regras_base,
    prompts_especialistas, carregar_capacidades_ia,carregar_usuario
)
from jarvis.utils.texto import monta_historico_slim, parece_recusa
from jarvis.utils.motor_latex import latex_para_unicode
from jarvis.ia.roteador import interpreta_comando_rapido, comprime_memoria
from jarvis.integracoes.controle_pc import executar_acao_pc, ferramentas_controle_pc, NOMES_ACOES_PC
from jarvis.memoria.embeddings import gerar_embedding
from jarvis.memoria.banco import buscar_contexto, registrar_turno, sincronizar_historico
from jarvis.memoria.resumos import iniciar_resumos_em_segundo_plano

from jarvis.memoria.persistencia import carregar_historico, salvar_historico
from jarvis.integracoes.google_calendar import (
    adicionar_multiplos_eventos, apagar_eventos_por_termo,
    editar_evento_por_termo, listar_proximos_eventos,
)
from jarvis.web.pesquisa_web import pesquisa_web
from jarvis.config import ARQUIVO_SCHEMA_FERRAMENTAS, USAR_LOCAL
from jarvis.build_flags import USAR_RPA
import re

with open(ARQUIVO_SCHEMA_FERRAMENTAS, "r", encoding="utf-8") as _f:
    ferramentas_jarvis = json.load(_f)["ferramentas_jarvis"]

ferramentas = ferramentas_jarvis + (ferramentas_controle_pc if USAR_RPA else [])

PALAVRAS_PC = (
    "abrir", "abre ", "clique", "clicar", "mouse", "tecla", "digite", "digitar",
    "arquivo", "pasta", "tela", "print", "screenshot", "instal", "fechar",
    "programa", "site", "url", "link",
)

modelo_nuvem = "openai/gpt-oss-120b"

executores_ferramentas = {
    "adicionar_multiplos_eventos": lambda a: adicionar_multiplos_eventos(eventos=a.get("eventos", [])),
    "apagar_eventos_por_termo": lambda a: apagar_eventos_por_termo(termo_busca=a.get("termo_busca")),
    "editar_evento_por_termo": lambda a:editar_evento_por_termo(
        termo_busca=a.get("termo_busca"),
        novo_resumo=a.get("novo_resumo"),
        nova_data_hora_inicio= a.get("nova_data_hora_inicio"),
        nova_data_hora_fim= a.get("nova_data_hora_fim"),
        novo_lembrete_minutos=a.get("novo_lembrete_minutos"),
    ),
    "listar_proximos_eventos":lambda a: listar_proximos_eventos(
        termo_busca=a.get("termo_busca"), dias_frente=a.get("dias_frente", 90)
    ),
    "pesquisar_na_web": lambda a: pesquisa_web(pergunta=a.get("pergunta"))
}

class motor_pensamento:
    def __init__(self, on_evento=None, on_texto=None, confirmar_pc = None):
        self._ferramentas_atuais = ferramentas_jarvis
        self.historico = carregar_historico()
        sincronizar_historico(self.historico)
        iniciar_resumos_em_segundo_plano()
        self.memoria_curto_p = ""
        self.modo_ia = "auto" if USAR_LOCAL else "nuvem"  # auto, local, nuvem
        self.capacidades_ia = carregar_capacidades_ia()
        self.usuario = carregar_usuario()
        self._on_evento = on_evento or (lambda tipo, **kw: None)
        self._on_texto = on_texto or (lambda pedaco: None)
        self._cancelar_evento = threading.Event()  # <- novo
        self._confirmar_pc = confirmar_pc

    def esquecer_memoria_curta(self):
        self.memoria_curto_p = ""

    def cancelar(self):
        self._cancelar_evento.set()

    def definir_modo(self, modo):
        modos_validos = ("auto", "local", "nuvem") if USAR_LOCAL else ("nuvem",)
        if modo in modos_validos:
            self.modo_ia = modo
            return True
        return False

    def ferramentas_para(self, pergunta):
        if USAR_RPA and any(p in pergunta.lower() for p in PALAVRAS_PC):
            return ferramentas_jarvis + ferramentas_controle_pc
        return ferramentas_jarvis

    def processar(self, pergunta, ignora_intencao=False, intencao_forcada=None):
        self._cancelar_evento.clear()
        self._ferramentas_atuais = self.ferramentas_para(pergunta)

        t_inicio = time.time()

        intencao = intencao_forcada or {"comando": "normal", "especialidade": "geral"}

        if not ignora_intencao and intencao_forcada is None:
            self._emit("interpretando_comando")
            intencao = interpreta_comando_rapido(pergunta)

        if intencao.get("comando") == "buscar_memoria":
            self.busca_comprime_memoria(pergunta, formato_resgate=True)

        self.historico.append({
            "role": "user",
            "content": pergunta,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        })

        # Orçamento de token pra caber histórico + resposta no limite da conta Groq
        def _lixo(m):
            c = (m.get("content") or "").strip().lower().rstrip(".")
            return m.get("role") == "assistant" and (
                c == "eu não sei" or parece_recusa(c) or c.startswith("não consegui concluir")
            )

        historico_limpo = [m for m in self.historico if not _lixo(m)]
        historico_enxuto = monta_historico_slim(historico_limpo, orcamento_token=1000)
        resposta_final = self.acorda_ia_repescagem(pergunta, historico_enxuto, intencao)

        resposta_formatada = latex_para_unicode(resposta_final)

        self.salvar_resposta(pergunta, resposta_final)

        duracao = time.time() - t_inicio
        self._emit("resposta_pronta", duracao=duracao)

        return {
            "resposta": resposta_final,
            "resposta_formatada": resposta_formatada,
            "duracao": duracao,
            "intencao": intencao,
        }



        # ----------------- memória -----------------

    def busca_comprime_memoria(self, pergunta, formato_resgate):
        self._emit("buscando_memoria")
        contexto = buscar_contexto(pergunta)
        if not contexto:
            self._emit("memoria_nao_encontrada")
            return False
        self.memoria_curto_p = f"--- CONTEXTO RESGATADO ---\n{contexto}\n--------------------------"
        self._emit("memoria_encontrada", resumo=contexto)
        return True

    def acorda_ia_repescagem(self, pergunta, historico_enxuto, intencao):
        resposta = self._acorda_ia(pergunta, historico_enxuto, intencao)

        if (("eu não sei" in resposta.lower().strip() or parece_recusa(resposta))
                and self.memoria_curto_p == ""):
            self._emit("repescagem_iniciada")
            if self.busca_comprime_memoria(pergunta, formato_resgate=False):
                self._emit("repescagem_encontrada")
                resposta = self._acorda_ia(pergunta, historico_enxuto, intencao)
            else:
                self._emit("repescagem_vazia")

        return resposta

    def _acorda_ia(self, pergunta, historico_enxuto, intencao):
        info_api = self.montar_mensagens(historico_enxuto, intencao)

        if self.modo_ia == "local":
            return self.chamar_local(info_api)

        try:
            return self.chamar_nuvem_com_retry(info_api)
        except Exception as erro_groq:
            erro_str = str(erro_groq)
            if USAR_LOCAL and self.modo_ia == "auto" and ("413" in erro_str or "429" in erro_str):
                self._emit("fallback_local", motivo=erro_str)
                info_local = self.montar_mensagens_fallback_local(info_api, pergunta, historico_enxuto)
                try:
                    return self.chamar_local(info_local)
                except Exception as erro_local:
                    self.historico.pop()
                    raise erro_local
            if "tool call validation failed" in erro_str.lower():
                self._emit("erro_ferramenta", erro=erro_str)
                self.historico.pop()
                return "Tentei usar uma ferramenta mas montei o pedido errado. Pode repetir a pergunta?"

            self._emit("erro_nuvem", erro=erro_str)
            self.historico.pop()
            raise

    def montar_mensagens(self, historico_enxuto, intencao):
        especialidade = intencao.get("especialidade", "geral")
        prompt_dinamico = regras_base + " " + prompts_especialistas.get(
            especialidade, prompts_especialistas["geral"]
        )

        info_api = [{"role": "system", "content": prompt_dinamico}]
        if self.usuario:
            info_api.append({"role":"system", "content":self.usuario})
        if self.capacidades_ia:
            info_api.append({"role": "system", "content": self.capacidades_ia})
        if self.memoria_curto_p:
            info_api.append({
                "role": "system",
                "content": (
                    "ATENÇÃO MÁXIMA: O usuário está te perguntando sobre um assunto do passado. "
                    "AJA COMO SE VOCÊ SE LEMBRASSE DE TUDO DE FORMA NATURAL! NUNCA diga "
                    "'como um modelo de IA', 'não tenho memória', ou 'eu não sei' para esta "
                    f"pergunta. Use os dados resgatados abaixo:\n\n{self.memoria_curto_p}"
                ),
            })
        for info in historico_enxuto:
            info_api.append({"role": info.get("role", "user"), "content": info.get("content", "")})
        return info_api

    def montar_mensagens_fallback_local(self, info_api, pergunta, historico_enxuto):
        # Mesmo espírito do fallback original: um payload mais enxuto pro Ollama.
        info_local = [info_api[0]]
        for msg in info_api[1:]:
            if msg.get("role") == "system" and "ATENÇÃO MÁXIMA" in msg.get("content", ""):
                info_local.append(msg)
        for hist in historico_enxuto[-4:]:
            if hist.get("role") == "assistant" and parece_recusa(hist.get("content", "")):
                continue
            info_local.append({"role": hist.get("role", "user"), "content": hist.get("content", "")})
        if info_local[-1]["content"] != pergunta:
            info_local.append({"role": "user", "content": pergunta})
        return info_local

    def _segundos_para_retry(self, erro):
        erro = str(erro)
        m = re.search(r"try again in ([\d.]+)(ms|s)", erro)
        if "429" not in erro or not m:
            return None
        segundos = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
        return segundos + 0.5 if segundos <= 30 else None

    def chamar_nuvem_com_retry(self, info_api, tentativas=2):
        for i in range(tentativas + 1):
            try:
                return self.chamar_nuvem(info_api)
            except Exception as e:
                espera = self._segundos_para_retry(e)
                if espera is not None and i < tentativas:
                    time.sleep(espera)
                    continue
                raise

    def chamar_nuvem(self, info_api):
        self._emit("pensando", destino="nuvem")
        '''with open("debug_tokens.txt", "a", encoding="utf-8") as _d:
            _d.write(f"--- chamada | tools: {len(self._ferramentas_atuais)} "
                     f"(~{len(json.dumps(self._ferramentas_atuais, ensure_ascii=False)) // 3} tok)\n")
            for m in info_api:
                _d.write(f"{m['role']}: ~{len(str(m.get('content') or '')) // 3} tok\n")'''

        completion = client.chat.completions.create(
            model=modelo_nuvem,
            messages=info_api,
            temperature=0.7,
            tools=self._ferramentas_atuais,
            tool_choice="auto",
            max_completion_tokens=800,
            top_p=1,
            stream=True,
            reasoning_format="parsed",
            reasoning_effort="low"
        )
        resposta, ferramentas_acionadas = self.consumir_stream(completion)
        if ferramentas_acionadas:
            resposta = self.resolver_ferramentas(info_api, ferramentas_acionadas, client, modelo_nuvem)
        return resposta

    def chamar_local(self, info_api):
        self._emit("pensando", destino="local")
        completion_local = client_local.chat.completions.create(
            model=modelo_local,
            messages=info_api,
            temperature=0.7,
            tools=self._ferramentas_atuais,
            tool_choice="auto",
            stream=True,
            timeout=60.0,
        )
        resposta, ferramentas_acionadas = self.consumir_stream(completion_local)
        if ferramentas_acionadas:
            resposta = self.resolver_ferramentas(info_api, ferramentas_acionadas, client_local, modelo_local)
        return resposta

    def consumir_stream(self, completion):
        resposta = ""
        ferramentas_acionadas = {}
        for chunk in completion:
            if self._cancelar_evento.is_set():
                self._emit("cancelado")
                break
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                resposta += delta.content
                self._on_texto(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in ferramentas_acionadas:
                        ferramentas_acionadas[idx] = {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "",
                        }
                    elif tc.function.arguments:
                        ferramentas_acionadas[idx]["arguments"] += tc.function.arguments
        return resposta, ferramentas_acionadas

        # ----------------- ferramentas (calendário,controle) -----------------

    def executar_ferramenta(self, nome, argumentos_json):
        try:
            argumentos = json.loads(argumentos_json)
        except Exception as e:
            return f"erro ao interpretaro argumentos de {nome}: {e}"

        if USAR_RPA and nome in NOMES_ACOES_PC:
            try:
                if self._confirmar_pc:
                    return executar_acao_pc(nome, argumentos, confirmar=self._confirmar_pc)
                return executar_acao_pc(nome,argumentos)
            except Exception as e:
                return f"erro na ação de controle de pc {nome}: {e}"
        executor = executores_ferramentas.get(nome)
        if not executor:
            return f"Ferramenta desconhecida {nome}"
        try:
            return executor(argumentos)
        except Exception as e:
            return f"Erro na função {nome}: {e}"

    def resolver_ferramentas(self, info_api, ferramentas_acionadas, client_usado, modelo_usado, max_rodada =5):
        rodada = 0

        contagem_nomes_total = {}
        while ferramentas_acionadas and rodada <max_rodada:
            if self._cancelar_evento.is_set():
                self._emit("cancelado")
                return "Cancelado pelo usuário."
            rodada+=1
            self._emit("acionando_ferramentas", ferramentas=[f["name"] for f in ferramentas_acionadas.values()])

            info_api.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in ferramentas_acionadas.values()
                ],
            })

            resultados_desta_rodada = []
            for tc in ferramentas_acionadas.values():
                resultado = self.executar_ferramenta(tc["name"], tc["arguments"])
                self._emit("ferramenta_executada", nome=tc["name"], resultado=str(resultado))
                contagem_nomes_total[tc["name"]] = contagem_nomes_total.get(tc["name"], 0) + 1

                if contagem_nomes_total[tc["name"]] > 1:
                    self._emit("ferramenta_repetida", nome=tc["name"], vezes=contagem_nomes_total[tc["name"]])

                resultados_desta_rodada.append(str(resultado))
                info_api.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": str(resultado),
                })

            self._emit("recebendo_confirmacao_final")
            kwargs = dict(model=modelo_usado, messages=info_api, temperature=0.7,
                          stream=True)
            if client_usado is client:
                kwargs["max_completion_tokens"] = 800

                kwargs["reasoning_format"] = "parsed"
                kwargs["reasoning_effort"] = "low"
            else:
                kwargs["timeout"] = 60.0

            try:
                completion_final = client_usado.chat.completions.create(**kwargs)
                resposta_final, ferramentas_acionadas = self.consumir_stream(completion_final)
            except Exception as erro_final:

                self._emit("erro_nuvem", erro=str(erro_final))
                return "\n".join(resultados_desta_rodada)

        return resposta_final or "Não consegui concluir a solicitação completa - muitas ações"

    def salvar_resposta(self, pergunta, resposta_final):
        texto_vetorizar = f"Usuário: {pergunta} | IA: {resposta_final}"
        embedding_resposta = gerar_embedding(texto_vetorizar)
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.historico.append({
            "role": "assistant",
            "content": resposta_final,
            "data": agora,
            "embedding": embedding_resposta,
        })
        salvar_historico(self.historico)
        registrar_turno(pergunta, resposta_final, agora, embedding_resposta)

        # ----------------- eventos -----------------

    def _emit(self, tipo, **dados):
        self._on_evento(tipo, **dados)

