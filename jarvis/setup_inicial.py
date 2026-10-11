import os
import shutil
import subprocess
from getpass import getpass
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from dotenv import dotenv_values, set_key

from jarvis.caminhos import PASTA_APP

ARQUIVO_ENV = os.path.join(PASTA_APP, ".env")
MODELOS_LOCAIS = ["qwen2.5:latest", "qwen2.5vl:7b", "moondream"]
url_ollama_win = "https://ollama.com/download/OllamaSetup.exe"
url_ollama_linux = "https://ollama.com/install.sh"
url_ollama_servidor = "http://localhost:11434"

espaco_min_gb = 15

_abridor_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def _gravar(chave, valor):
    set_key(ARQUIVO_ENV, chave, valor, quote_mode="never")


def _perguntar_sim_nao(texto, padrao=False):
    sufixo = "[S/n]" if padrao else "[s/N]"
    resp = input(f"{texto} {sufixo} ").strip().lower()
    if not resp:
        return padrao
    return resp in ("s", "sim", "y", "yes")

def _achar_ollama():
    """Acha o executável do Ollama (no Windows o PATH só atualiza em terminais novos)."""
    caminho = shutil.which("ollama")
    if caminho:
        return caminho
    if sys.platform == "win32":
        candidato = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidato.is_file():
            return str(candidato)
    return None

def _instalar_ollama():
    if sys.platform == "win32":
        print("📥 Instalando o Ollama no Windows (não precisa de administrador)...")
        if shutil.which("winget"):
            subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent",
                            "--accept-package-agreements", "--accept-source-agreements"])

        if _achar_ollama() is None:
            instalador = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            try:
                print("   Baixando o instalador oficial...")
                urllib.request.urlretrieve(url_ollama_win, instalador)
            except Exception as e:
                print(f"⚠️ Falha ao baixar o instalador: {e}")
                return None
            subprocess.run([instalador, "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])

    elif sys.platform.startswith("linux"):
        if shutil.which("curl") is None:
            print("⚠️ 'curl' não encontrado. Instale-o (ex.: sudo apt install curl) e tente de novo.")
            return None
        print("        Instalando o Ollama no Linux (vai pedir a sua senha de administrador)...")
        subprocess.run(f"curl -fsSL {url_ollama_linux} | sh", shell=True)
    else:
        print(" Instalação automática só para Windows e Linux. Baixe em https://ollama.com/download")
        return None
    return _achar_ollama()

def _servidor_ativo():
    try:
        _abridor_local.open(url_ollama_servidor, timeout=2)
        return True
    except Exception:
        return False

def _garantir_servidor(ollama):
    if _servidor_ativo():
        return True
    print("⏳ Iniciando o servidor do Ollama...")
    if sys.platform == "win32":
        extras = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)
                  | getattr(subprocess, "DETACHED_PROCESS", 0)}
    else:
        extras = {"start_new_session": True}
    subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **extras)
    for _ in range(30):
        time.sleep(1)
        if _servidor_ativo():
            return True
    return False

def _baixar_modelos(ollama):
    ok = True
    for m in MODELOS_LOCAIS:
        print(f"⬇️ Baixando {m} ...")
        if subprocess.run([ollama, "pull", m]).returncode != 0:
            print(f"⚠️ Falha ao baixar {m}.")
            ok = False
    return ok


def _instalar_local():
    livre = shutil.disk_usage(os.path.expanduser("~")).free / 1024 ** 3
    if livre < espaco_min_gb:
        print(f"⚠️ Só há {livre:.0f} GB livres e o modelo local precisa de cerca de {espaco_min_gb} GB.")
        if not _perguntar_sim_nao("Continuar mesmo assim?"):
            return False
    ollama = _achar_ollama() or _instalar_ollama()
    if ollama is None:
        print("⚠️ Não foi possível instalar o Ollama automaticamente.")
        print("Instale em https://ollama.com/download e rode a configuração de novo.")
        return False
    if not _garantir_servidor(ollama):
        print("     O servidor do Ollama não iniciou.")
        return False
    return _baixar_modelos(ollama)


def configurar_primeira_vez():
    env = dotenv_values(ARQUIVO_ENV) if os.path.exists(ARQUIVO_ENV) else {}

    # --- Key da Groq ---
    if not env.get("GROQ_API_KEY"):
        print("🔑 Configuração inicial")
        print("Crie sua key grátis em https://console.groq.com/keys")
        while True:
            chave = getpass("Cole sua GROQ_API_KEY (não aparece enquanto digita): ").strip()
            chave = chave.strip('"').strip("'")
            if chave:
                break
            print("⚠️ A key não pode ficar vazia.")
        _gravar("GROQ_API_KEY", chave)

    if "USAR_LOCAL" not in env:
        print("\n🧠 Modelo local (Ollama)")
        print("Funciona offline e serve de reserva quando a Groq atinge o limite,")
        print("mas baixa cerca de 13 GB e pede uma máquina razoável")
        print("(8 GB de RAM no mínimo, 16 GB de preferência; GPU é opcional).")


        if _perguntar_sim_nao("Quer usar o modelo local?"):
            if _instalar_local():
                _gravar("USAR_LOCAL", "true")
                print("modelo local pronto!")
            else:
                print("modelo local não ficou pronto. Seguindo apenas com a nuvem;")
        else:
            _gravar("USAR_LOCAL", "false")
