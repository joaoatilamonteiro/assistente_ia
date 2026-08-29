import json
import os

from jarvis.config import arquivo_memoria


def carregar_historico():
    if os.path.exists(arquivo_memoria):
        try:
            with open(arquivo_memoria, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"\n Deu erro ao ler a memoria\nErro: {e}")
            return []
    return []


def salvar_historico(historico):
    os.makedirs(os.path.dirname(arquivo_memoria), exist_ok=True)
    with open(arquivo_memoria, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=4)
