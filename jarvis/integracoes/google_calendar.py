"""Integração com o Google Calendar: criar, editar e apagar eventos."""
import datetime
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from jarvis.config import ARQUIVO_TOKEN

ESCOPO_CALENDAR = ['https://www.googleapis.com/auth/calendar']


def editar_evento_por_termo(termo_busca, novo_resumo=None, nova_data_hora_inicio=None, nova_data_hora_fim=None,
                            novo_lembrete_minutos=None):
    """Busca eventos futuros com o termo informado e atualiza TODOS eles em massa."""
    if not os.path.exists(ARQUIVO_TOKEN):
        return "Erro: Arquivo token.json não encontrado."

    try:
        creds = Credentials.from_authorized_user_file(ARQUIVO_TOKEN, ESCOPO_CALENDAR)
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
    if not os.path.exists(ARQUIVO_TOKEN):
        return "Erro: Arquivo token.json não encontrado."

    try:
        creds = Credentials.from_authorized_user_file(ARQUIVO_TOKEN, ESCOPO_CALENDAR)
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
    if not os.path.exists(ARQUIVO_TOKEN):
        return "Erro: Arquivo token.json não encontrado. A agenda não está autenticada."

    try:
        creds = Credentials.from_authorized_user_file(ARQUIVO_TOKEN, ESCOPO_CALENDAR)
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
