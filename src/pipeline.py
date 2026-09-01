"""Orquestrador do pipeline: seeds, bronze, silver, gold, checks.

Idempotencia: toda tabela e criada com CREATE OR REPLACE e o banco e recriado
do zero a cada execucao a partir das fontes. Rodar duas vezes seguidas produz
byte-a-byte o mesmo conteudo, o que e verificado pelo teste de idempotencia.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import duckdb
import pandas as pd

import bronze
import fx
from config import (CANAIS_SEM_ATRIBUICAO, DATA_CORTE, DUCKDB_PATH, MAPA_CANAL,
                    MAPA_PLANO, PERIODO_FIM, PERIODO_INI, PRECO_TABELA, SQL_DIR)

log = logging.getLogger(__name__)

ORDEM_SQL = [
    "00_macros.sql",
    "10_silver_cambio.sql",
    "20_silver_clientes.sql",
    "30_silver_assinaturas.sql",
    "40_silver_faturas.sql",
    "50_silver_caixa_infra.sql",
    "60_gold_receita_caixa.sql",
    "70_gold_mrr.sql",
    "80_gold_margem.sql",
    "90_gold_unit_economics.sql",
    "95_naive.sql",
]


def abrir(reset: bool = True) -> duckdb.DuckDBPyConnection:
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if reset and DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
        log.info("warehouse anterior removido (execucao do zero)")
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("SET TimeZone='UTC'")   # logs de nuvem em fuso local causariam
    return con                          # deslocamento de mes na virada


def _dim_mes() -> pd.DataFrame:
    """Grade mensal. Comeca antes da janela de analise porque a decomposicao de
    MRR precisa do mes anterior, e ha assinaturas e competencias de 2022/2023.
    """
    ini = date(2022, 1, 1)
    linhas, atual, ordem = [], ini, 0
    while atual <= date(2026, 12, 1):
        prox = (atual.replace(day=28) + timedelta(days=4)).replace(day=1)
        linhas.append({
            "mes": atual.strftime("%Y-%m"),
            "ordem_mes": ordem,
            "ini_mes": atual,
            "fim_mes": prox - timedelta(days=1),
            "dentro_da_janela": PERIODO_INI <= atual <= PERIODO_FIM,
        })
        atual, ordem = prox, ordem + 1
    return pd.DataFrame(linhas)


def carregar_seeds(con: duckdb.DuckDBPyConnection, cotacoes: dict[str, float]) -> None:
    """Seeds e parametros. Ficam como tabela para que o SQL nao tenha constante
    literal espalhada: mudar a data de corte e uma alteracao em um lugar so.
    """
    log.info("--- seeds e parametros ---")

    con.register("_dim", _dim_mes())
    con.execute("CREATE OR REPLACE TABLE seed_dim_mes AS SELECT * FROM _dim")
    con.unregister("_dim")

    con.execute("CREATE OR REPLACE TABLE seed_parametros AS "
                "SELECT ?::DATE AS data_corte, ?::DATE AS periodo_ini, ?::DATE AS periodo_fim",
                [DATA_CORTE, PERIODO_INI, PERIODO_FIM])

    con.register("_plano", pd.DataFrame(
        [{"plano_bruto": k, "plano_padrao": v} for k, v in MAPA_PLANO.items()]))
    con.execute("CREATE OR REPLACE TABLE seed_mapa_plano AS SELECT * FROM _plano")
    con.unregister("_plano")

    con.register("_canal", pd.DataFrame(
        [{"canal_bruto": k, "canal_padrao": v} for k, v in MAPA_CANAL.items()]))
    con.execute("CREATE OR REPLACE TABLE seed_mapa_canal AS SELECT * FROM _canal")
    con.unregister("_canal")

    con.register("_sem_atr", pd.DataFrame([{"canal": c} for c in CANAIS_SEM_ATRIBUICAO]))
    con.execute("CREATE OR REPLACE TABLE seed_canal_sem_atribuicao AS SELECT * FROM _sem_atr")
    con.unregister("_sem_atr")

    con.register("_preco", pd.DataFrame(
        [{"plano": p, "moeda": m, "preco_tabela": v} for (p, m), v in PRECO_TABELA.items()]))
    con.execute("CREATE OR REPLACE TABLE seed_preco_tabela AS SELECT * FROM _preco")
    con.unregister("_preco")

    serie = fx.serie_diaria_preenchida(cotacoes)
    con.register("_fx", pd.DataFrame(serie, columns=["data", "taxa", "preenchida"]))
    con.execute("CREATE OR REPLACE TABLE bronze_fx_diario AS "
                "SELECT data::DATE AS data, taxa::DOUBLE AS taxa, preenchida::BOOLEAN AS preenchida FROM _fx")
    con.unregister("_fx")
    log.info("seed_dim_mes, parametros, mapas de dominio e cambio carregados")


def executar_sql(con: duckdb.DuckDBPyConnection) -> None:
    for arquivo in ORDEM_SQL:
        caminho = SQL_DIR / arquivo
        if not caminho.exists():
            raise FileNotFoundError(f"script SQL ausente: {caminho}")
        log.info("executando %s", arquivo)
        con.execute(caminho.read_text(encoding="utf-8"))


def rodar(forcar_fx: bool = False) -> duckdb.DuckDBPyConnection:
    cotacoes = fx.carregar_ptax(forcar_refresh=forcar_fx)
    con = abrir(reset=True)
    carregar_seeds(con, cotacoes)
    bronze.executar(con)
    executar_sql(con)
    log.info("pipeline concluido: %s", DUCKDB_PATH)
    return con
