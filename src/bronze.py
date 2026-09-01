"""Camada bronze: ingestao fiel das fontes, sem regra de negocio.

Principios desta camada:
  1. Nada e corrigido aqui. Todo campo entra como texto, exatamente como veio,
     para que qualquer numero final possa ser confrontado com a fonte crua.
  2. Cada linha carrega linhagem (arquivo de origem, linha fisica, hash da linha)
     e o momento da ingestao.
  3. Idempotencia por CREATE OR REPLACE: rodar duas vezes produz a mesma tabela,
     nunca duplica.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import sqlite3
from pathlib import Path

import duckdb

from config import (SRC_ASSINATURAS, SRC_FATURAS, SRC_INFRA, SRC_SQLITE, SRC_WSMAP)

log = logging.getLogger(__name__)

ENCODINGS = ("utf-8", "cp1252", "latin-1")


def ler_texto(path: Path) -> tuple[str, str]:
    """Le arquivo tentando encodings em ordem. Retorna (texto, encoding_usado).

    faturas_export.csv esta em cp1252, os demais em utf-8. Assumir utf-8 para
    todos quebra a ingestao com UnicodeDecodeError na primeira linha do arquivo.
    """
    bruto = path.read_bytes()
    for enc in ENCODINGS:
        try:
            txt = bruto.decode(enc)
            if enc != "utf-8":
                log.warning("%s nao e utf-8, decodificado como %s", path.name, enc)
            return txt, enc
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("nenhum", b"", 0, 1, f"encoding desconhecido em {path}")


def _h(linha: str) -> str:
    return hashlib.sha256(linha.encode("utf-8", "replace")).hexdigest()[:16]


def _gravar(con: duckdb.DuckDBPyConnection, tabela: str, registros: list[dict]) -> None:
    """Grava lista de dicts como tabela bronze, todas as colunas VARCHAR."""
    if not registros:
        raise ValueError(f"fonte vazia para {tabela}")
    cols = list(registros[0].keys())
    con.register("_stage", _para_arrowable(registros, cols))
    ddl = ", ".join(f'"{c}" VARCHAR' for c in cols)
    con.execute(f"CREATE OR REPLACE TABLE {tabela} ({ddl})")
    con.execute(f"INSERT INTO {tabela} SELECT {', '.join(f'\"{c}\"' for c in cols)} FROM _stage")
    con.unregister("_stage")
    log.info("bronze.%s: %d linhas, %d colunas", tabela, len(registros), len(cols))


def _para_arrowable(registros: list[dict], cols: list[str]):
    """Converte para DataFrame de strings; None preservado como NULL."""
    import pandas as pd
    return pd.DataFrame(
        [{c: (None if r.get(c) is None else str(r.get(c))) for c in cols} for r in registros],
        columns=cols, dtype="object",
    )


# ------------------------------------------------------------------ faturas
def ingerir_faturas(con: duckdb.DuckDBPyConnection) -> None:
    """CSV com preambulo de relatorio, separador ';' e rodape de totalizacao.

    O arquivo nao e um CSV limpo: 5 linhas de cabecalho humano antes do header
    real e 1 linha de rodape ('Total de registros: 1417'). Localizamos o header
    por conteudo em vez de fixar skiprows, para nao quebrar se o preambulo mudar
    de tamanho no proximo export.
    """
    txt, enc = ler_texto(SRC_FATURAS)
    linhas = txt.splitlines()
    idx = next((i for i, l in enumerate(linhas) if l.startswith("numero_fatura;")), None)
    if idx is None:
        raise ValueError("header 'numero_fatura;...' nao encontrado em faturas_export.csv")
    if idx != 5:
        log.warning("preambulo com %d linhas (esperado 5), header localizado dinamicamente", idx)

    leitor = csv.DictReader(io.StringIO("\n".join(linhas[idx:])), delimiter=";")
    registros, descartadas = [], []
    for n, r in enumerate(leitor, start=idx + 2):
        # rodape do export: primeira coluna preenchida, todas as outras nulas
        if r.get("id_cliente") is None and r.get("valor_liquido") is None:
            descartadas.append((n, r.get("numero_fatura")))
            continue
        r["_arquivo"] = SRC_FATURAS.name
        r["_encoding"] = enc
        r["_linha_fisica"] = n
        r["_hash_linha"] = _h(json.dumps(r, sort_keys=True, default=str))
        registros.append(r)

    for n, conteudo in descartadas:
        log.warning("faturas linha %d descartada como rodape de export: %r", n, conteudo)
    _gravar(con, "bronze_faturas", registros)
    con.execute("CREATE OR REPLACE TABLE bronze_faturas_descartes AS "
                "SELECT * FROM (VALUES " +
                (", ".join(f"({n}, '{(c or '').replace(chr(39), chr(39) * 2)}')" for n, c in descartadas)
                 if descartadas else "(NULL, NULL)") +
                ") t(linha_fisica, conteudo)")


# -------------------------------------------------------------- assinaturas
def ingerir_assinaturas(con: duckdb.DuckDBPyConnection) -> None:
    """JSONL. Campos com tipo instavel (seats int|str, unit_price float|str)
    entram como texto para que a coercao seja explicita e testavel na silver."""
    txt, enc = ler_texto(SRC_ASSINATURAS)
    registros = []
    for n, linha in enumerate(txt.splitlines(), start=1):
        if not linha.strip():
            continue
        try:
            obj = json.loads(linha)
        except json.JSONDecodeError as exc:
            log.error("assinaturas linha %d ilegivel, descartada: %s", n, exc)
            continue
        obj["_arquivo"] = SRC_ASSINATURAS.name
        obj["_encoding"] = enc
        obj["_linha_fisica"] = n
        obj["_hash_linha"] = _h(linha)
        registros.append(obj)
    # uniao de chaves: protege contra JSONL com schema irregular entre linhas
    chaves = sorted({k for r in registros for k in r})
    registros = [{k: r.get(k) for k in chaves} for r in registros]
    _gravar(con, "bronze_assinaturas", registros)


# ---------------------------------------------------------------- infra/map
def _ingerir_csv_simples(con: duckdb.DuckDBPyConnection, path: Path, tabela: str) -> None:
    txt, enc = ler_texto(path)
    registros = []
    for n, r in enumerate(csv.DictReader(io.StringIO(txt)), start=2):
        r["_arquivo"] = path.name
        r["_encoding"] = enc
        r["_linha_fisica"] = n
        r["_hash_linha"] = _h(json.dumps(r, sort_keys=True, default=str))
        registros.append(r)
    _gravar(con, tabela, registros)


def ingerir_infra(con: duckdb.DuckDBPyConnection) -> None:
    _ingerir_csv_simples(con, SRC_INFRA, "bronze_infra_costs")
    _ingerir_csv_simples(con, SRC_WSMAP, "bronze_workspace_map")


# ------------------------------------------------------------------- sqlite
def ingerir_sqlite(con: duckdb.DuckDBPyConnection) -> None:
    """Le as tres tabelas do banco financeiro. Usamos sqlite3 nativo em vez do
    extension scan do DuckDB para nao depender de download de extensao em
    ambiente sem rede, mantendo o pipeline executavel offline apos o cache de FX.
    """
    sq = sqlite3.connect(f"file:{SRC_SQLITE}?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row
    try:
        tabelas = [r[0] for r in sq.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        log.info("sqlite: tabelas encontradas %s", tabelas)
        for t in tabelas:
            registros = []
            for n, row in enumerate(sq.execute(f'SELECT * FROM "{t}"'), start=1):
                r = {k: row[k] for k in row.keys()}
                r["_arquivo"] = SRC_SQLITE.name
                r["_encoding"] = "sqlite"
                r["_linha_fisica"] = n
                r["_hash_linha"] = _h(json.dumps(r, sort_keys=True, default=str))
                registros.append(r)
            _gravar(con, f"bronze_{t}", registros)
    finally:
        sq.close()


def executar(con: duckdb.DuckDBPyConnection) -> None:
    log.info("--- camada bronze ---")
    ingerir_faturas(con)
    ingerir_assinaturas(con)
    ingerir_infra(con)
    ingerir_sqlite(con)
