
import sys
import os

# Permite rodar este script diretamente (python scripts/vetorizar_historico.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis.memoria.persistencia import carregar_historico, salvar_historico
from jarvis.memoria.embeddings import gerar_embedding


def main():
    historico = carregar_historico()

    if not historico:
        print("📭 historico.json vazio ou inexistente. Nada para vetorizar.")
        return

    atualizados = 0
    for msg in historico:
        if not msg.get("embedding"):
            texto = f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
            msg["embedding"] = gerar_embedding(texto)
            atualizados += 1

    if atualizados:
        salvar_historico(historico)
        print(f"✅ {atualizados} mensagem(ns) vetorizada(s) e salvas em data/historico.json.")
    else:
        print("✅ Todas as mensagens já tinham embedding. Nada a fazer.")


if __name__ == "__main__":
    main()
