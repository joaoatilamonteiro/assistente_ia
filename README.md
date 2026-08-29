# IA-cat (Jarvis)

Assistente de IA local/nuvem com memória semântica, leitura de documentos/imagens
e integração com o Google Calendar.

## Estrutura do projeto

```
IA-cat/
├── data/
│   ├── historico.json          # memória das conversas (gerado em runtime)
│   └── credenciais/
│       ├── credenciais.json    # OAuth Client ID do Google Cloud Console
│       └── token.json          # gerado por jarvis/integracoes/autenticar_google.py
├── docs/
│   └── CAPACIDADES_IA.md       # texto injetado como system prompt (capacidades)
├── jarvis/
│   ├── entrada/                # entrada do usuário: loop de conversa e captura de tela
│   │   ├── loop_conversa.py    # iniciar_conversa() — o coração do chat
│   │   └── captura_tela.py     # pega a última print tirada
│   ├── ia/                     # chamadas de IA
│   │   ├── visao.py            # leitura óptica de imagens (local + fallback nuvem)
│   │   ├── roteador.py         # classifica a intenção da pergunta e comprime memória
│   │   └── ferramentas.py      # schema das tools (function calling) do calendário
│   ├── integracoes/            # integrações externas
│   │   ├── google_calendar.py  # criar/editar/apagar eventos
│   │   ├── groq_status.py      # saúde/limites da API Groq
│   │   └── autenticar_google.py# script de autenticação OAuth (rodar 1x)
│   ├── memoria/                # memória semântica
│   │   ├── embeddings.py       # gerar embeddings, busca semântica, RAG de documentos
│   │   └── persistencia.py     # carregar/salvar o historico.json
│   ├── utils/                  # utilitários genéricos
│   │   ├── animacao.py         # LoadingAnimado
│   │   └── texto.py            # corte de histórico, detecção de recusa/resposta ruim
│   ├── voz/                    # reconhecimento de fala (identificacaodefala.py)
│   ├── web/                    # renderização de respostas em HTML
│   │   ├── renderizador.py
│   │   └── template.html
│   └── config.py               # env, paths, clientes de IA, regras e prompts base
├── scripts/
│   ├── importar_conversa.py    # importa uma conversa externa para data/historico.json
│   └── vetorizar_historico.py  # gera embeddings faltantes no historico.json
├── main.py                     # ponto de entrada (chama jarvis.entrada.iniciar_conversa)
├── requirements.txt
└── .gitignore
```

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate <- caso esteja no Windows
source .venv/Scripts/actiavate <- caso esteja no Linux/MacOs
  
pip install -r requirements.txt
python jarvis/integracoes/autenticar_google.py   # só na primeira vez
python main.py
```
