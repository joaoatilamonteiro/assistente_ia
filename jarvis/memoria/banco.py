"""Memória de longo prazo do Jarvis: SQLite + busca híbrida (FTS5 + vetores).

Uma tabela só (`docs`) guarda dois tipos de documento:
  - 'turno'  : um par pergunta/resposta da conversa
  - 'resumo' : resumo de UM dia, gerado uma vez (ver resumos.py)

Busca:
  - pergunta com data (dd/mm ou dd/mm/aaaa) -> resumo do dia; sem resumo, os turnos do dia
  - pergunta sem data -> híbrido (palavra-chave BM25 + vetor), fundidos por RRF,
    com resumos primeiro e turnos depois
Nada aqui chama IA na hora da pergunta.
"""
import hashlib
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime

import numpy as np

CAMINHO_DB = None  # None = data/memoria.db (via jarvis.config). Sobrescreva em testes.

_lock_escrita = threading.Lock()
_lock_cache = threading.Lock()
_cache = None  # (ids, tipos, matriz normalizada) - recarregado após qualquer escrita
_tem_fts = True

_STOPWORDS = {
    "que", "com", "uma", "uns", "umas", "para", "por", "dos", "das", "nos", "nas", "mas",
    "eu", "voce", "você", "voces", "vocês", "contigo", "comigo", "nosso", "nossa", "gente",
    "dia", "aquele", "aquela", "sobre", "como", "qual", "quais", "quando", "onde", "mais",
    "foi", "era", "tem", "tinha", "isso", "esse", "essa", "aqui", "tava", "estava", "estavamos",
    "estávamos", "fazendo", "falando", "falei", "falamos", "fiz", "fizemos", "disse", "lembra",
    "lembrar", "conversa", "conversamos", "conversando", "aconteceu", "coisa", "algo", "pra",
    "ontem", "hoje", "antes", "aquilo", "tudo", "nada", "ter", "seu", "sua", "meu", "minha",
}


# ----------------------------------------------------------------- conexão
def _caminho():
    if CAMINHO_DB:
        return CAMINHO_DB
    from jarvis.config import PASTA_DATA
    os.makedirs(PASTA_DATA, exist_ok=True)
    return os.path.join(PASTA_DATA, "memoria.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(_caminho(), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _garantir_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _garantir_schema(conn):
    global _tem_fts
    conn.execute("""
        CREATE TABLE IF NOT EXISTS docs(
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo    TEXT NOT NULL,
            chave   TEXT UNIQUE NOT NULL,
            dia     TEXT,
            data    TEXT,
            usuario TEXT,
            ia      TEXT,
            texto   TEXT NOT NULL,
            emb     BLOB
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_dia ON docs(dia, tipo)")
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
            USING fts5(texto, tokenize='unicode61 remove_diacritics 2')""")
    except sqlite3.OperationalError:
        _tem_fts = False  # SQLite sem FTS5: segue só com vetor


# ----------------------------------------------------------------- utilidades
def _embed(texto):
    try:
        from jarvis.memoria.embeddings import gerar_embedding
        return gerar_embedding(texto)
    except Exception:
        return None


def _dia_iso(data_str):
    try:
        return datetime.strptime((data_str or "")[:10], "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def _br(dia_iso):
    try:
        return datetime.strptime(dia_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return dia_iso or "?"


def _cortar(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


_FALHAS = ("não consegui fazer a pesquisa", "não consegui pesquisar", "não consegui concluir",
           "tentei usar uma ferramenta", "falha no processamento")


def _eh_lixo(pergunta, ia):
    """Turnos sem valor de memória: erros, 'Eu não sei' e trocas minúsculas (oi, tudo bem...)."""
    c = (ia or "").strip().lower()
    if not c or len((pergunta or "").strip()) + len(c) < 80:
        return True
    return c.rstrip(".") == "eu não sei" or c.startswith(_FALHAS)


def extrair_datas(pergunta):
    """[(dia, mes, ano|None)] para cada dd/mm ou dd/mm/aaaa válido na pergunta."""
    achados = []
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", pergunta or ""):
        d, mo = int(m.group(1)), int(m.group(2))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            continue
        ano = m.group(3)
        if ano:
            ano = int(ano) + (2000 if len(ano) <= 2 else 0)
        achados.append((d, mo, ano))
    return achados


# ----------------------------------------------------------------- escrita
def _inserir(conn, tipo, chave, dia, data, usuario, ia, texto, emb):
    blob = np.asarray(emb, dtype=np.float32).tobytes() if emb is not None else None
    with _lock_escrita:
        cur = conn.execute(
            "INSERT OR IGNORE INTO docs(tipo,chave,dia,data,usuario,ia,texto,emb) VALUES(?,?,?,?,?,?,?,?)",
            (tipo, chave, dia, data, usuario, ia, texto, blob))
        if cur.rowcount and _tem_fts:
            conn.execute("INSERT INTO docs_fts(rowid, texto) VALUES(?,?)", (cur.lastrowid, texto))
    return bool(cur.rowcount)


def _invalidar_cache():
    global _cache
    with _lock_cache:
        _cache = None


def registrar_turno(pergunta, resposta, data_str=None, embedding=None, _conexao=None):
    """Guarda um par pergunta/resposta. Devolve True se era novo."""
    if _eh_lixo(pergunta, resposta):
        return False
    data_str = data_str or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    texto = f"Usuário: {pergunta} | IA: {resposta}"
    chave = hashlib.sha1((data_str + texto).encode("utf-8")).hexdigest()
    if embedding is None:
        embedding = _embed(texto)

    def _fazer(conn):
        return _inserir(conn, "turno", chave, _dia_iso(data_str), data_str, pergunta, resposta, texto, embedding)

    if _conexao is not None:
        novo = _fazer(_conexao)
    else:
        with _conn() as conn:
            novo = _fazer(conn)
    if novo:
        _invalidar_cache()
    return novo


def sincronizar_historico(historico):
    """Importa pro banco os pares do historico.json que ainda não estão lá (idempotente)."""
    novos, i = 0, 0
    with _conn() as conn:
        while i < len(historico) - 1:
            u, a = historico[i], historico[i + 1]
            if u.get("role") == "user" and a.get("role") == "assistant":
                if registrar_turno(u.get("content", ""), a.get("content", ""),
                                   a.get("data"), a.get("embedding"), _conexao=conn):
                    novos += 1
                i += 2
            else:
                i += 1
    return novos


# ----------------------------------------------------------------- resumos diários
def dias_sem_resumo(limite=20, minimo_turnos=2):
    """Dias passados (hoje não conta) com conversa suficiente e sem resumo, mais recentes primeiro."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT t.dia FROM docs t
            WHERE t.tipo='turno' AND t.dia IS NOT NULL AND t.dia < ?
              AND NOT EXISTS (SELECT 1 FROM docs r WHERE r.tipo='resumo' AND r.dia=t.dia)
            GROUP BY t.dia HAVING COUNT(*) >= ?
            ORDER BY t.dia DESC LIMIT ?""", (date.today().isoformat(), minimo_turnos, limite)).fetchall()
    return [r[0] for r in rows]


def texto_do_dia(dia, max_chars=6000):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT usuario, ia FROM docs WHERE tipo='turno' AND dia=? ORDER BY id", (dia,)).fetchall()
    linhas, total = [], 0
    for u, a in rows:
        linha = f"Você: {_cortar(u, 300)} | Adomo: {_cortar(a, 300)}"
        if total + len(linha) > max_chars:
            break
        linhas.append(linha)
        total += len(linha)
    return "\n".join(linhas)


def salvar_resumo(dia, resumo):
    resumo = (resumo or "").strip()
    if not resumo:
        return False
    with _conn() as conn:
        novo = _inserir(conn, "resumo", f"resumo:{dia}", dia, None, None, None, resumo, _embed(resumo))
    if novo:
        _invalidar_cache()
    return novo


# ----------------------------------------------------------------- busca
def _vetores(conn):
    global _cache
    with _lock_cache:
        if _cache is None:
            rows = conn.execute("SELECT id, tipo, emb FROM docs WHERE emb IS NOT NULL").fetchall()
            if rows:
                ids = np.array([r[0] for r in rows])
                tipos = np.array([r[1] for r in rows])
                matriz = np.vstack([np.frombuffer(r[2], dtype=np.float32) for r in rows])
                matriz = matriz / np.maximum(np.linalg.norm(matriz, axis=1, keepdims=True), 1e-10)
                _cache = (ids, tipos, matriz)
            else:
                _cache = (np.array([]), np.array([]), None)
        return _cache


def _busca_vetorial(conn, q_vec, tipo, k, minimo=0.25):
    if q_vec is None:
        return []
    try:
        ids, tipos, matriz = _vetores(conn)
        if matriz is None:
            return []
        q = np.asarray(q_vec, dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-10)
        sims = matriz @ q
        idx = np.where((tipos == tipo) & (sims > minimo))[0]
        idx = idx[np.argsort(sims[idx])[::-1]][:k]
        return [int(ids[i]) for i in idx]
    except Exception:
        return []  # ex.: embeddings de modelos diferentes misturados


def _busca_palavras(conn, pergunta, tipo, k):
    if not _tem_fts:
        return []
    termos = [t for t in re.findall(r"\w{3,}", (pergunta or "").lower())
              if t not in _STOPWORDS and not t.isdigit()]
    if not termos:
        return []
    consulta = " OR ".join('"%s"' % t.replace('"', "") for t in dict.fromkeys(termos))
    try:
        rows = conn.execute("""
            SELECT d.id FROM docs_fts f JOIN docs d ON d.id = f.rowid
            WHERE docs_fts MATCH ? AND d.tipo = ?
            ORDER BY bm25(docs_fts) LIMIT ?""", (consulta, tipo, k)).fetchall()
        return [r[0] for r in rows]
    except sqlite3.OperationalError:
        return []


def _rrf(listas, k=60):
    pontos = {}
    for lista in listas:
        for pos, id_ in enumerate(lista):
            pontos[id_] = pontos.get(id_, 0.0) + 1.0 / (k + pos + 1)
    return sorted(pontos, key=pontos.get, reverse=True)


def _linhas_por_id(conn, ids):
    out = []
    for id_ in ids:
        r = conn.execute("SELECT tipo, dia, usuario, ia, texto FROM docs WHERE id=?", (id_,)).fetchone()
        if r:
            out.append(r)
    return out


def _formatar(linha):
    tipo, dia, usuario, ia, texto = linha
    if tipo == "resumo":
        return f"[{_br(dia)}] RESUMO DO DIA: {texto}"
    return f"[{_br(dia)}] Você: {_cortar(usuario, 250)} | Adomo: {_cortar(ia, 350)}"


def _contexto_por_datas(conn, datas):
    blocos = []
    for d, mo, ano in datas:
        padrao = f"{ano:04d}-{mo:02d}-{d:02d}" if ano else f"%-{mo:02d}-{d:02d}"
        dias = [r[0] for r in conn.execute(
            "SELECT DISTINCT dia FROM docs WHERE dia LIKE ? ORDER BY dia DESC LIMIT 2", (padrao,))]
        for dia in dias:
            resumo = conn.execute(
                "SELECT tipo, dia, usuario, ia, texto FROM docs WHERE tipo='resumo' AND dia=?", (dia,)).fetchone()
            if resumo:
                blocos.append(_formatar(resumo))
                continue
            for linha in conn.execute(
                    "SELECT tipo, dia, usuario, ia, texto FROM docs WHERE tipo='turno' AND dia=? ORDER BY id",
                    (dia,)):
                blocos.append(_formatar(linha))
    return blocos


def _contexto_hibrido(conn, pergunta):
    q_vec = _embed(pergunta)
    blocos = []
    for tipo, k in (("resumo", 2), ("turno", 3)):
        ids = _rrf([_busca_palavras(conn, pergunta, tipo, k * 3),
                    _busca_vetorial(conn, q_vec, tipo, k * 3)])[:k]
        blocos += [_formatar(l) for l in _linhas_por_id(conn, ids)]
    return blocos


def buscar_contexto(pergunta, max_chars=2400):
    """Texto pronto pra entrar no prompt, ou '' se não achou nada. Sem chamar IA."""
    with _conn() as conn:
        datas = extrair_datas(pergunta)
        # Com data explícita, só vale o que for daquele dia: nada de "chute" semântico.
        blocos = _contexto_por_datas(conn, datas) if datas else _contexto_hibrido(conn, pergunta)
    saida, total = [], 0
    for b in blocos:
        if total + len(b) > max_chars:
            sobra = max_chars - total
            if sobra > 200:
                saida.append(b[:sobra].rstrip() + "…")
            break
        saida.append(b)
        total += len(b)
    return "\n\n".join(saida)