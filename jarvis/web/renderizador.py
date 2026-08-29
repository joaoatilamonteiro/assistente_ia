
import os
import tempfile
import webbrowser

# template.html mora nesta mesma pasta (jarvis/web/)
CAMINHO_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")


def renderizar_no_navegador(texto_da_ia):
    # Trata as barras e crases para não quebrar o script JavaScript no HTML
    texto_seguro = texto_da_ia.replace('\\', '\\\\\\\\').replace('`', '\\`').replace('\n', '\\n')

    try:
        with open(CAMINHO_TEMPLATE, "r", encoding="utf-8") as f:
            template_html = f.read()
    except FileNotFoundError:
        print("❌ Erro: O arquivo 'template.html' não foi encontrado em jarvis/web/!")
        return

    # Substitui a tag do template pelo texto tratado da IA
    html_content = template_html.replace("{{TEXTO_SEGURO}}", texto_seguro)

    # Salva na pasta temporária do sistema para exibição
    pasta_temp = tempfile.gettempdir()
    caminho_arquivo = os.path.join(pasta_temp, "jarvis_resolucao.html")

    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("🌐 Abrindo documento formatado no navegador...")
    webbrowser.open(f"file://{caminho_arquivo}")
