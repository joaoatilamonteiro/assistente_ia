"""Captura da última print tirada, usada pelo comando \\print no chat."""
from pathlib import Path


def pega_print():
    caminho_da_pasta = Path(r"C:\Users\monte\Pictures\Screenshots")
    arquivos = [f for f in caminho_da_pasta.iterdir() if f.is_file()]

    if arquivos:
        arquivos_ordenados = sorted(arquivos, key=lambda x: x.stat().st_mtime)

        ultimo_arquivo = arquivos_ordenados[-1]

        ultimo_arquivo_abs = ultimo_arquivo.absolute()

        return ultimo_arquivo_abs

    else:
        print("pasta vazia")
