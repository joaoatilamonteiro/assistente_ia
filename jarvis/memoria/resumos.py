"""Resumos diários: cada dia passado é resumido UMA vez, em segundo plano, e guardado no banco.
Na hora da pergunta a busca só lê o resumo pronto - nenhuma chamada de IA."""
import re
import threading
import time

from jarvis.config import USAR_LOCAL, client, client_local, modelo_local
from jarvis.memoria import banco

_PROMPT = (
    "Você resume um dia de conversa entre o usuário e seu assistente. Escreva em português, em no máximo "
    "6 linhas curtas: os assuntos tratados, o que foi decidido, problemas e soluções, e dados técnicos "
    "importantes (nomes, comandos, versões, arquivos). Sem saudações e sem enrolação."
)

_iniciado = False


def _resumir(bruto, dia_iso):
    mensagens = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": f"DIA {banco._br(dia_iso)}\n\n{bruto}"},
    ]
    if USAR_LOCAL:
        # Local não gasta o limite de tokens por minuto da Groq.
        r = client_local.chat.completions.create(
            model=modelo_local, messages=mensagens, temperature=0.3, max_tokens=400, timeout=120)
    else:
        r = client.chat.completions.create(
            model="openai/gpt-oss-120b", messages=mensagens, temperature=0.3,
            max_completion_tokens=500, reasoning_format="parsed", reasoning_effort="low")
    return (r.choices[0].message.content or "").strip()


def _espera_429(erro):
    erro = str(erro)
    m = re.search(r"try again in ([\d.]+)(ms|s)", erro)
    if "429" not in erro or not m:
        return None
    segundos = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
    return segundos + 1 if segundos <= 60 else None


def _resumir_com_retry(bruto, dia):
    for tentativa in range(3):
        try:
            return _resumir(bruto, dia)
        except Exception as e:
            espera = _espera_429(e)
            if espera is None or tentativa == 2:
                return None
            time.sleep(espera)
    return None


def gerar_resumos_pendentes(pausa=65):
    for dia in banco.dias_sem_resumo():
        bruto = banco.texto_do_dia(dia)
        if not bruto:
            continue
        resumo = _resumir_com_retry(bruto, dia)
        if resumo:
            banco.salvar_resumo(dia, resumo)
        time.sleep(pausa)  # um dia por minuto: não disputa o limite da Groq com você


def _loop(atraso):
    time.sleep(atraso)  # deixa o app abrir e estabilizar
    try:
        gerar_resumos_pendentes()
    except Exception:
        pass  # segunda tentativa no próximo início; nunca derruba o app


def iniciar_resumos_em_segundo_plano(atraso=60):
    global _iniciado
    if _iniciado:
        return
    _iniciado = True
    threading.Thread(target=_loop, args=(atraso,), daemon=True).start()