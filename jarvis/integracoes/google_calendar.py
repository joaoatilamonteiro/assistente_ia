"""Integração com o Google Calendar: criar, editar e apagar eventos."""
import datetime
import os
from calendar import calendar

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import max_retries

from jarvis.config import ARQUIVO_TOKEN, ARQUIVO_CREDENCIAIS, PASTA_CREDENCIAIS

ESCOPO_CALENDAR = ['https://www.googleapis.com/auth/calendar']


def obter_credenciais_google():
    """Garante credenciais válidas do Google Calendar, sem exigir que você
    rode autenticar_google.py manualmente antes:

    - Se já existe token.json e ele expirou, renova sozinho pelo
      refresh_token e salva de volta no arquivo (sem abrir navegador).
    - Se não existe token.json (primeira vez) ou o refresh_token morreu/foi
      revogado, abre o navegador NA HORA pra você autorizar - e só então a
      função que chamou isso continua (criar/editar/apagar evento).
    """
    creds = None

    if os.path.exists(ARQUIVO_TOKEN):
        creds = Credentials.from_authorized_user_file(ARQUIVO_TOKEN, ESCOPO_CALENDAR)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None  # refresh token morreu/foi revogado - cai pro login completo abaixo

    if not creds or not creds.valid:
        if not os.path.exists(ARQUIVO_CREDENCIAIS):
            print(f"❌ Não encontrei '{ARQUIVO_CREDENCIAIS}'. Baixe o OAuth Client ID "
                  "no Google Cloud Console (APIs & Services > Credentials) e coloque lá.")
            return None

        print("🌐 Primeira vez usando o calendário (ou o acesso expirou) - "
              "abrindo o navegador pra você autorizar...")
        flow = InstalledAppFlow.from_client_secrets_file(ARQUIVO_CREDENCIAIS, ESCOPO_CALENDAR)
        creds = flow.run_local_server(port=0)

    os.makedirs(PASTA_CREDENCIAIS, exist_ok=True)
    with open(ARQUIVO_TOKEN, "w") as token_file:
        token_file.write(creds.to_json())

    return creds


def editar_evento_por_termo(termo_busca, novo_resumo=None, nova_data_hora_inicio=None, nova_data_hora_fim=None,
                            novo_lembrete_minutos=None):
    """Busca eventos futuros com o termo informado e atualiza TODOS eles em massa."""
    creds = obter_credenciais_google()
    if not creds:
        return "Erro: não consegui autenticar com o Google. Verifique se data/credenciais/credenciais.json existe."

    try:
        service = build('calendar', 'v3', credentials=creds)

        # 1. Busca TODOS os eventos sem maxResults
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now, q=termo_busca,
            singleEvents=True, orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        if not events:
            return f"Nenhum evento futuro encontrado contendo '{termo_busca}' para editar."

        # 2. Prepara o pacote de mudanças
        mudancas = {}
        if novo_resumo:
            mudancas['summary'] = novo_resumo
        if nova_data_hora_inicio:
            mudancas['start'] = {'dateTime': nova_data_hora_inicio, 'timeZone': 'America/Fortaleza'}
        if nova_data_hora_fim:
            mudancas['end'] = {'dateTime': nova_data_hora_fim, 'timeZone': 'America/Fortaleza'}

        # O BUG DO LEMBRETE VAZIO FOI ARRUMADO AQUI:
        if novo_lembrete_minutos is not None:
            mudancas['reminders'] = {
                'useDefault': False,
                'overrides': [{'method': 'popup', 'minutes': novo_lembrete_minutos}]
            }

        if not mudancas:
            return "Nenhuma alteração foi solicitada pela IA."

        # 3. Executa a edição para CADA evento encontrado
        nomes_editados = []
        for evento_alvo in events:
            service.events().patch(
                calendarId='primary', eventId=evento_alvo['id'], body=mudancas
            ).execute()
            nomes_editados.append(evento_alvo.get('summary'))

        return f"Sucesso! {len(nomes_editados)} eventos editados: {', '.join(nomes_editados)}."
    except Exception as e:
        return f"Erro ao editar evento: {str(e)}"


def apagar_eventos_por_termo(termo_busca):
    """Busca eventos futuros que contenham o termo no título e os apaga."""
    creds = obter_credenciais_google()
    if not creds:
        return "Erro: não consegui autenticar com o Google. Verifique se data/credenciais/credenciais.json existe."

    try:
        service = build('calendar', 'v3', credentials=creds)

        # Busca eventos futuros que batem com a palavra-chave
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now, q=termo_busca,
            singleEvents=True, orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return f"Nenhum evento encontrado contendo '{termo_busca}' para apagar."

        apagados = []
        for event in events:
            # Comando de aniquilação do Google API
            service.events().delete(calendarId='primary', eventId=event['id']).execute()
            apagados.append(event['summary'])

        return f"Sucesso! Apaguei {len(apagados)} evento(s): {', '.join(apagados)}."
    except Exception as e:
        return f"Erro ao apagar evento: {str(e)}"


def adicionar_multiplos_eventos(eventos):
    """Cria vários eventos no Google Calendar de uma vez através de uma lista."""
    creds = obter_credenciais_google()
    if not creds:
        return "Erro: não consegui autenticar com o Google. Verifique se data/credenciais/credenciais.json existe."

    try:
        service = build('calendar', 'v3', credentials=creds)

        # O FOR MÁGICO DO LADO DO PYTHON
        for evt in eventos:
            evento_body = {
                'summary': evt.get('resumo'),
                'start': {
                    'dateTime': evt.get('data_hora_inicio'),
                    'timeZone': 'America/Fortaleza',
                },
                'end': {
                    'dateTime': evt.get('data_hora_fim'),
                    'timeZone': 'America/Fortaleza',
                },
            }

            if evt.get('lembrete_minutos'):
                evento_body['reminders'] = {
                    'useDefault': False,
                    'overrides': [{'method': 'popup', 'minutes': evt.get('lembrete_minutos')}]
                }

            service.events().insert(calendarId='primary', body=evento_body).execute()
        return f"Sucesso! {len(eventos)} eventos foram adicionados ao calendário."

    except Exception as e:
        return f"Erro ao acessar o Google Calendar: {str(e)}"

def listar_proximos_eventos(termo_busca = None, dias_frente = 90):
    creds = obter_credenciais_google()
    if not creds:
        return "Erro: não consegui autenticar com o google. Verifique se data/credenciais.json existe"

    try:
        service = build("calendar", "v3", credentials=creds)
        agora = datetime.datetime.utcnow()
        limite = agora+datetime.timedelta(days=dias_frente)

        events_result = service.events().list(
            calendarId = "primary",
            timeMin = agora.isoformat() + "Z",
            timeMax = limite.isoformat() + "Z",
            q = termo_busca,
            maxResults = 20,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        if not events:
            if termo_busca:
                return f"nenhum evento futuro encontrado contendo {termo_busca} nos proximos {dias_frente} dias"
            return f"nenhum evento encontrado nos proximos {dias_frente} dias"

        linhas = []
        for event in events:
            inicio = event["start"].get("dateTime", event["start"].get("data"))
            linhas.append(f"-{event.get('summary', '(sem titulo)')}: {inicio}")
        return f"Eventos encontrados: \n\n{linhas}"

    except Exception as e:
        return f"erro ao listar {str(e)}"