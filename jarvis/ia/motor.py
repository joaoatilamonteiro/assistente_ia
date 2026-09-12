import json
import time
from datetime import datetime

from jarvis.config import (
    client_local, client, modelo_local, regras_base,
    prompts_especialistas, carregar_capacidades_ia,carregar_usuario
)
from jarvis.utils.texto import monta_historico_slim, parece_recusa
from jarvis.utils.motor_latex import latex_para_unicode
from jarvis.ia.roteador import interpreta_comando_rapido, comprime_memoria
from jarvis.ia.ferramentas import ferramentas_jarvis
from jarvis.integracoes.controle_pc import executar_acao_pc, ferramentas_controle_pc, NOMES_ACOES_PC
from jarvis.memoria.embeddings import gerar_embedding, buscar_memoria_semantica
from jarvis.memoria.persistencia import carregar_historico, salvar_historico
from jarvis.integracoes.google_calendar import (
    adicionar_multiplos_eventos, apagar_eventos_por_termo,
    editar_evento_por_termo, listar_proximos_eventos,
)
from jarvis.web.pesquisa_web import pesquisa_web

ferramentas = ferramentas_jarvis + ferramentas_controle_pc

modelo_nuvem = "openai/gpt-oss-120b"

executores_ferramentas = {
    "adicionar_multiplos_eventos": lambda a: adicionar_multiplos_eventos(eventos=a.get("eventos", [])),
    "apagar_eventos_por_termo": lambda a: apagar_eventos_por_termo(termo_busca=a.get("termo_busca")),
    "editar_eventos_por_termo": lambda a:editar_evento_por_termo(
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
        self.historico = carregar_historico()
        self.memoria_curto_p = ""
        self.modo_ia = "auto"  # auto, local, nuvem
        self.capacidades_ia = carregar_capacidades_ia()
        self.usuario = carregar_usuario()
        self._on_evento = on_evento or (lambda tipo, **kw: None)
        self._on_texto = on_texto or (lambda pedaco: None)

        self._confirmar_pc = confirmar_pc

    def esquecer_memoria_curta(self):
        self.memoria_curto_p = ""

    def definir_modo(self, modo):
        if modo in ("auto", "local", "nuvem"):
            self.modo_ia = modo
            return True
        return False

    def processar(self, pergunta, ignora_intencao=False, intencao_forcada=None):
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
        historico_enxuto = monta_historico_slim(self.historico, orcamento_token=2500)

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
        memoria_resgatada = buscar_memoria_semantica(pergunta, self.historico)
        if not memoria_resgatada:
            self._emit("memoria_nao_encontrada")
            return False

        if formato_resgate:
            bruto = "".join(
                f"[{m.get('data', '')}] {m.get('role', '').upper()}: {m.get('content')}\n\n"
                for m in memoria_resgatada
            )
        else:
            bruto = "".join(
                f"[{m.get('role', '').upper()}]: {m.get('content')}\n" for m in memoria_resgatada
            )

        self._emit("comprimindo_memoria")
        contexto_comprimido = comprime_memoria(bruto)
        self.memoria_curto_p = f"--- CONTEXTO RESGATADO ---\n{contexto_comprimido}\n--------------------------"
        self._emit("memoria_encontrada", resumo=contexto_comprimido)
        return True

        # ----------------- chamada de IA -----------------

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
            return self.chamar_nuvem(info_api)
        except Exception as erro_groq:
            erro_str = str(erro_groq)
            if self.modo_ia == "auto" and ("413" in erro_str or "429" in erro_str):
                self._emit("fallback_local", motivo=erro_str)
                info_local = self.montar_mensagens_fallback_local(info_api, pergunta, historico_enxuto)
                try:
                    return self.chamar_local(info_local)
                except Exception as erro_local:
                    self.historico.pop()
                    raise erro_local
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
        if len(info_api) > 1 and "ATENÇÃO MÁXIMA" in info_api[1].get("content", ""):
            info_local.append(info_api[1])
        for hist in historico_enxuto[-4:]:
            if hist.get("role") == "assistant" and parece_recusa(hist.get("content", "")):
                continue
            info_local.append({"role": hist.get("role", "user"), "content": hist.get("content", "")})
        if info_local[-1]["content"] != pergunta:
            info_local.append({"role": "user", "content": pergunta})
        return info_local

    def chamar_nuvem(self, info_api):
        self._emit("pensando", destino="nuvem")
        completion = client.chat.completions.create(
            model=modelo_nuvem,
            messages=info_api,
            temperature=0.7,
            tools=ferramentas,
            tool_choice="auto",
            max_completion_tokens=2000,
            top_p=1,
            stream=True,
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
            tools=ferramentas,
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

        if nome in NOMES_ACOES_PC:
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

        while ferramentas_acionadas and rodada <max_rodada:
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

            for tc in ferramentas_acionadas.values():
                resultado = self.executar_ferramenta(tc["name"], tc["arguments"])
                self._emit("ferramenta_executada", nome=tc["name"], resultado=str(resultado))
                info_api.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": str(resultado),
                })

            self._emit("recebendo_confirmacao_final")
            kwargs = dict(model=modelo_usado, messages=info_api, temperature=0.7,
                          tools=ferramentas, tool_choice = "auto",stream=True)
            if client_usado is client:
                kwargs["max_completion_tokens"] = 2000
            else:
                kwargs["timeout"] = 60.0

            completion_final = client_usado.chat.completions.create(**kwargs)
            resposta_final, ferramentas_acionadas = self.consumir_stream(completion_final)
        return resposta_final or "Não consegui concluir a solicitação completa - muitas ações"

        # ----------------- persistência -----------------

    def salvar_resposta(self, pergunta, resposta_final):
        texto_vetorizar = f"Usuário: {pergunta} | IA: {resposta_final}"
        embedding_resposta = gerar_embedding(texto_vetorizar)
        self.historico.append({
            "role": "assistant",
            "content": resposta_final,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "embedding": embedding_resposta,
        })
        salvar_historico(self.historico)

        # ----------------- eventos -----------------

    def _emit(self, tipo, **dados):
        self._on_evento(tipo, **dados)

