"""
Script de autenticação inicial do Google Calendar.

Roda esse script UMA VEZ (ou toda vez que o token.json precisar ser
recriado do zero - ex: depois de publicar o app, ou se o refresh token
for revogado). Ele abre o navegador, pede pra você logar e autorizar o
acesso ao Calendar, e salva o resultado em data/credenciais/token.json -
que é o arquivo que jarvis.integracoes.google_calendar usa depois pra
falar com o Calendar sem precisar abrir navegador de novo.

Requisitos:
- O arquivo data/credenciais/credenciais.json (baixado do Google Cloud
  Console em APIs & Services > Credentials > seu OAuth Client ID).
- pip install google-auth-oauthlib --break-system-packages
  (se ainda não tiver instalado)
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from jarvis.config import ARQUIVO_CREDENCIAIS, ARQUIVO_TOKEN, PASTA_CREDENCIAIS

# Mesmo escopo usado em jarvis/integracoes/google_calendar.py - se um dia
# precisar de mais permissões (ex: Gmail), adicione aqui E lá, os dois têm que bater.
SCOPES = ['https://www.googleapis.com/auth/calendar']


def main():
    if not os.path.exists(ARQUIVO_CREDENCIAIS):
        print(f"❌ Não encontrei '{ARQUIVO_CREDENCIAIS}'.")
        print("   Baixe o OAuth Client ID em: console.cloud.google.com > "
              "APIs & Services > Credentials, e coloque em data/credenciais/ com esse nome.")
        return

    if os.path.exists(ARQUIVO_TOKEN):
        resposta = input(f"⚠️ Já existe um '{ARQUIVO_TOKEN}'. Sobrescrever? (s/n) ").strip().lower()
        if resposta != 's':
            print("Cancelado. Nada foi alterado.")
            return

    print("🌐 Abrindo o navegador pra você fazer login e autorizar o acesso...")
    flow = InstalledAppFlow.from_client_secrets_file(ARQUIVO_CREDENCIAIS, SCOPES)
    creds = flow.run_local_server(port=0)

    os.makedirs(PASTA_CREDENCIAIS, exist_ok=True)
    with open(ARQUIVO_TOKEN, 'w') as token_file:
        token_file.write(creds.to_json())

    print(f"✅ Login concluído! '{ARQUIVO_TOKEN}' foi criado/atualizado com sucesso.")
    print("   Se o app já estiver publicado (status 'In production'), esse token")
    print("   não deve mais expirar em 7 dias.")


if __name__ == '__main__':
    main()
