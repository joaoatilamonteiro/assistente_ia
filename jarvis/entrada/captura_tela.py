from pathlib import Path



def pega_print():
    caminho_da_pasta = Path.home() / "Pictures" / "Screenshots"
    if not caminho_da_pasta.is_dir():
        print("pasta de prints não encontrada")
        return None

    arquivos = [f for f in caminho_da_pasta.iterdir() if f.is_file()]

    if arquivos:
        arquivos_ordenados = sorted(arquivos, key=lambda x: x.stat().st_mtime)

        ultimo_arquivo = arquivos_ordenados[-1]

        ultimo_arquivo_abs = ultimo_arquivo.absolute()

        return ultimo_arquivo_abs

    else:
        print("pasta vazia")
