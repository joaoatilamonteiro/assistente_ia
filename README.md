# IA-cat (Jarvis / Adomo)

Assistente de IA local/nuvem com memória semântica, leitura de documentos/imagens,
integração com o Google Calendar e controle de mouse/teclado (RPA), rodando numa
interface de terminal (TUI).

## Como funciona (visão geral)

- **Nuvem**: usa a [Groq](https://groq.com/) (API compatível com OpenAI) para respostas
  rápidas com o modelo `openai/gpt-oss-120b`.
- **Local**: usa o [Ollama](https://ollama.com/) rodando na sua máquina como fallback
  (quando a Groq falhar, atingir limite de tokens/rate limit, ou no modo `local`),
  com o modelo `qwen2.5:latest` (texto) e `qwen2.5vl:7b` (visão).
- **Modos** (`\modo auto|local|nuvem` dentro da TUI): `auto` tenta nuvem e cai pro
  local se necessário; `local` e `nuvem` forçam um dos dois.
- **Memória semântica**: embeddings gerados com `sentence-transformers`
  (`all-MiniLM-L6-v2`), buscando conversas antigas relevantes por similaridade de
  cosseno.
- **Google Calendar**: criar, editar e apagar eventos via function calling
  (só disponível no modo nuvem).
- **Controle de PC (RPA)**: mover mouse, clicar, digitar, tirar screenshot, e ações
  sensíveis (enviar texto+Enter, deletar arquivo, instalar pacote, fechar janela)
  que exigem confirmação explícita antes de executar.

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
├── interface/
│   └── interface.py            # TUI (Textual): chat, sidebar de status/memória, comandos \
├── jarvis/
│   ├── entrada/
│   │   └── captura_tela.py     # pega a última print tirada
│   ├── ia/
│   │   ├── motor.py            # motor_pensamento: orquestra nuvem/local, ferramentas e memória
│   │   ├── visao.py            # leitura óptica de imagens (local + fallback nuvem)
│   │   ├── roteador.py         # classifica a intenção da pergunta e comprime memória
│   │   └── ferramentas.py      # schema das tools (function calling) do calendário
│   ├── integracoes/
│   │   ├── controle_pc.py      # RPA (pyautogui): mouse/teclado/arquivo/pacote, com confirmação
│   │   ├── google_calendar.py  # criar/editar/apagar eventos
│   │   ├── groq_status.py      # saúde/limites da API Groq
│   │   └── autenticar_google.py# script de autenticação OAuth (rodar 1x)
│   ├── memoria/
│   │   ├── embeddings.py       # gerar embeddings, busca semântica, RAG de documentos
│   │   └── persistencia.py     # carregar/salvar o historico.json
│   ├── utils/
│   │   ├── motor_latex.py      # converte LaTeX (\frac, \boxed, aligned, etc.) para unicode
│   │   ├── animacao.py         # LoadingAnimado
│   │   └── texto.py            # corte de histórico, detecção de recusa/resposta ruim
│   ├── voz/                    # reconhecimento de fala (identificacaodefala.py)
│   ├── web/                    # renderização de respostas em HTML
│   │   ├── renderizador.py
│   │   └── template.html
│   └── config.py               # env, paths, clientes de IA, regras e prompts base
├── scripts/
│   ├── cria_credencial.py
│   ├── importar_conversa.py    # importa uma conversa externa para data/historico.json
│   └── vetorizar_historico.py  # gera embeddings faltantes no historico.json
├── main.py                     # ponto de entrada — abre a TUI (interface.interface.JarvisTUI)
├── requirements.txt
└── .gitignore
```

## Pré-requisitos

- Python 3.10+
- Conta na [Groq](https://console.groq.com/) (gratuita) para a chave de API
- [Ollama](https://ollama.com/download) instalado, para o modo local/fallback
- Projeto no [Google Cloud Console](https://console.cloud.google.com/) com a
  Google Calendar API habilitada, para a integração com a agenda

## Configuração

### 1. Ambiente virtual e dependências

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/Scripts/activate  # Linux/macOS

pip install -r requirements.txt
```

### 2. Chave da API Groq

1. Crie uma conta em https://console.groq.com/ e gere uma API key em
   **API Keys**.
2. Na raiz do projeto, crie um arquivo `.env` (não versionado) com:

```
GROQ_API_KEY=sua_chave_aqui
```

### 3. Ollama (modelos locais)

1. Instale o Ollama: https://ollama.com/download
2. Baixe os modelos usados pelo projeto:

```bash
ollama pull qwen2.5:latest
ollama pull qwen2.5vl:7b
```

3. Deixe o Ollama rodando (por padrão ele sobe um servidor em
   `http://localhost:11434`, é isso que `jarvis/config.py` usa como
   `client_local`). Sem o Ollama ativo, o modo `local` e o fallback automático
   do modo `auto` não funcionam.

### 4. Google Calendar (opcional, mas necessário pras ferramentas de agenda)

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um
   projeto (ou use um existente) e habilite a **Google Calendar API**.
2. Em **Credenciais**, crie um **OAuth Client ID** do tipo *Desktop app*.
3. Baixe o JSON gerado e salve como `data/credenciais/credenciais.json`
   (crie as pastas `data/` e `data/credenciais/` se não existirem).
4. Rode a autenticação uma única vez (abre o navegador pra você logar com a
   conta Google que terá os eventos gerenciados):

```bash
python jarvis/integracoes/autenticar_google.py
```

Isso gera `data/credenciais/token.json`, usado nas próximas execuções sem
precisar logar de novo. Se não configurar isso, as ferramentas de calendário
simplesmente falham quando chamadas — o resto do assistente continua
funcionando normalmente.

## Como rodar

```bash
python main.py
```

Isso abre a TUI (interface de terminal). Atalhos principais: `Ctrl+S` envia a
mensagem, `Ctrl+T` alterna entre os modos `auto/local/nuvem`, `Ctrl+L` limpa a
conversa, `Ctrl+Q` sai.

Comandos disponíveis dentro do chat (prefixados por `\`):

| Comando            | O que faz                                             |
|--------------------|--------------------------------------------------------|
| `\modo auto\|local\|nuvem` | Troca o modo de execução                       |
| `\arquivo <caminho>` | Carrega um `.pdf`, `.txt` ou `.md` e resume/analisa   |
| `\print`           | Lê a última print tirada e transcreve o conteúdo       |
| `\saude`           | Mostra o status/limites atuais da API Groq             |
| `\esquece`         | Reseta a memória de curto prazo da conversa atual      |

## Controle de PC (RPA)

O assistente pode mover o mouse, clicar, digitar, tirar screenshot, e (com
confirmação obrigatória na própria TUI) enviar texto + Enter, apagar arquivos,
instalar pacotes e fechar a janela em foco. Ações sensíveis mostram a
descrição exata do que será feito e esperam você responder `sim`/`não` no
campo de mensagem antes de executar — essa confirmação está no código
(`jarvis/integracoes/controle_pc.py`) e não pode ser pulada pelo modelo.
