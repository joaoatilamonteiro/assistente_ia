"""
Importa um arquivo JSON externo (uma lista de mensagens no formato
[{"role": "user"/"assistant", "content": "..."}, ...]) para dentro do
data/historico.json, gerando embedding para cada mensagem importada.

Uso: python scripts/importar_conversa.py caminho/para/conversa.json
"""
import json
import sys
import os
from datetime import datetime

# Permite rodar este script diretamente (python scripts/importar_conversa.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis.memoria.persistencia import carregar_historico, salvar_historico
from jarvis.memoria.embeddings import gerar_embedding


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/importar_conversa.py caminho/para/conversa.json")
        return

    caminho_conversa = sys.argv[1]
    if not os.path.exists(caminho_conversa):
        print(f"❌ Arquivo não encontrado: {caminho_conversa}")
        return

    with open(caminho_conversa, "r", encoding="utf-8") as f:
        conversa_importada = json.load(f)

    historico = carregar_historico()

    importadas = 0
    for msg in conversa_importada:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue

        texto_vetorizar = f"{role.upper()}: {content}"
        historico.append({
            "role": role,
            "content": content,
            "data": msg.get("data", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
            "embedding": gerar_embedding(texto_vetorizar)
        })
        importadas += 1

    salvar_historico(historico)
    print(f"✅ {importadas} mensagem(ns) importada(s) para data/historico.json.")


if __name__ == "__main__":
    main()
