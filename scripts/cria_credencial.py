
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis.integracoes.google_calendar import obter_credenciais_google

creds = obter_credenciais_google()

if creds:
    print("✅ Autenticado com sucesso! token.json criado/atualizado.")
    print(f"   Válido: {creds.valid} | Expirado: {creds.expired}")
else:
    print("❌ Falhou. Verifique se data/credenciais/credenciais.json existe.")