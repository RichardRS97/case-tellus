"""Testes de reconciliacao executados como parte do pipeline.

Nao sao testes de unidade de funcao: sao assercoes sobre o resultado final.
A regra e a da pergunta 7 do enunciado: o que quebra o pipeline quando alguem
contraria uma definicao. Severidade ERRO derruba a execucao com codigo de saida
diferente de zero; severidade ALERTA e publicada no relatorio sem derrubar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import duckdb

log = logging.getLogger(__name__)

TOLERANCIA_BRL = 0.01     # centavo
TOLERANCIA_REL = 1e-9


@dataclass
class Resultado:
    nome: str
    severidade: str          # ERRO | ALERTA
    passou: bool
    detalhe: str
    valor: float | None = None


@dataclass
class Relatorio:
    itens: list[Resultado] = field(default_factory=list)

    @property
    def falhas_bloqueantes(self) -> list[Resultado]:
        return [i for i in self.itens if not i.passou and i.severidade == "ERRO"]

    @property
    def alertas(self) -> list[Resultado]:
        return [i for i in self.itens if not i.passou and i.severidade == "ALERTA"]


def _um(con, sql: str):
    r = con.execute(sql).fetchone()
    return None if r is None else r[0]


def executar(con: duckdb.DuckDBPyConnection) -> Relatorio:
    rel = Relatorio()

    def check(nome, severidade, condicao, detalhe, valor=None):
        rel.itens.append(Resultado(nome, severidade, bool(condicao), detalhe, valor))
        marca = "OK  " if condicao else ("FALHA" if severidade == "ERRO" else "ALERTA")
        log.log(logging.INFO if condicao else (logging.ERROR if severidade == "ERRO" else logging.WARNING),
                "[%s] %s | %s", marca, nome, detalhe)

    # ---------------------------------------------------------- unicidade
    for tabela, chave in (("silver_faturas", "numero_fatura"),
                          ("silver_assinaturas", "subscription_id"),
                          ("silver_clientes", "customer_id"),
                          ("silver_pagamentos", "payment_id"),
                          ("silver_entidades", "entidade_id")):
        n = _um(con, f"SELECT count(*) FROM (SELECT {chave} FROM {tabela} GROUP BY 1 HAVING count(*) > 1)")
        check(f"unicidade_{tabela}", "ERRO", n == 0, f"{n} valores de {chave} duplicados", n)

    n = _um(con, "SELECT count(*) FROM (SELECT mes, workspace_id, servico FROM silver_infra_custos "
                 "GROUP BY 1,2,3 HAVING count(*) > 1)")
    check("unicidade_infra", "ERRO", n == 0, f"{n} chaves (mes, workspace, servico) duplicadas", n)

    # -------------------------------------------- rateio de competencia fecha
    # A soma do rateio pro-rata tem que devolver exatamente o valor do documento.
    v = _um(con, """
        SELECT coalesce(max(abs(dif)), 0) FROM (
            SELECT r.numero_fatura,
                   sum(r.receita_moeda_origem) - max(r.valor_documento_moeda_origem) AS dif
            FROM silver_receita_reconhecida r GROUP BY 1)
    """)
    check("rateio_prorata_fecha", "ERRO", v is not None and v < TOLERANCIA_BRL,
          f"maior divergencia entre soma do rateio e valor do documento: {v:.6f}", v)

    # -------------------------------------------- decomposicao de MRR fecha
    v = _um(con, "SELECT coalesce(max(abs(residuo_decomposicao_brl)), 0) FROM gold_mrr_mensal")
    check("decomposicao_mrr_fecha", "ERRO", v is not None and v < 0.05,
          f"maior residuo da decomposicao de MRR: {v:.6f} BRL", v)

    # -------------------------------------------- bridge de erro fecha
    v = _um(con, """
        WITH p AS (SELECT valor_brl FROM gold_bridge_receita WHERE papel = 'partida'),
             a AS (SELECT coalesce(sum(valor_brl), 0) s FROM gold_bridge_receita WHERE papel = 'ajuste'),
             c AS (SELECT valor_brl FROM gold_bridge_receita WHERE papel = 'chegada')
        SELECT abs(((SELECT valor_brl FROM p) + (SELECT s FROM a)) - (SELECT valor_brl FROM c))
    """)
    check("bridge_receita_fecha", "ERRO", v is not None and v < 0.05,
          f"partida + ajustes - chegada = {v:.6f} BRL", v)

    # -------------------------------------------- sem receita orfa de cliente
    n = _um(con, "SELECT count(*) FROM silver_receita_reconhecida WHERE entidade_id IS NULL")
    check("receita_sem_entidade", "ERRO", n == 0, f"{n} linhas de receita sem entidade economica", n)

    # -------------------------------------------- cambio aplicado onde precisa
    n = _um(con, "SELECT count(*) FROM silver_receita_reconhecida WHERE moeda='USD' AND usd_brl_aplicado IS NULL")
    check("cambio_receita_usd", "ERRO", n == 0, f"{n} linhas em USD sem cotacao aplicada", n)
    n = _um(con, "SELECT count(*) FROM silver_infra_custos WHERE usd_brl_aplicado IS NULL")
    check("cambio_infra", "ERRO", n == 0, f"{n} linhas de infra sem cotacao aplicada", n)

    # -------------------------------------------- nenhuma receita negativa por erro de sinal
    n = _um(con, "SELECT count(*) FROM silver_receita_reconhecida WHERE tipo='FATURA' AND receita_brl < 0")
    check("sinal_faturas", "ERRO", n == 0, f"{n} faturas com receita negativa", n)
    n = _um(con, "SELECT count(*) FROM silver_receita_reconhecida WHERE tipo='NOTA_CREDITO' AND receita_brl > 0")
    check("sinal_notas_credito", "ERRO", n == 0, f"{n} notas de credito com receita positiva", n)

    # -------------------------------------------- preco fecha com tabela (P06)
    n = _um(con, """
        SELECT count(*) FROM silver_assinaturas_validas a
        LEFT JOIN seed_preco_tabela p ON p.plano = a.plano AND p.moeda = a.moeda
        WHERE p.preco_tabela IS NULL OR abs(a.unit_price - p.preco_tabela) > 0.01
    """)
    check("preco_dentro_da_tabela", "ERRO", n == 0,
          f"{n} assinaturas com unit_price fora do preco de tabela do plano/moeda", n)

    # -------------------------------------------- P07: sobreposicao real
    n = _um(con, "SELECT count(*) FROM alerta_sobreposicao_vigencia")
    check("sem_sobreposicao_vigencia", "ERRO", n == 0,
          f"{n} pares de assinaturas sobrepostas no mesmo cliente apos dedup", n)

    # -------------------------------------------- plano fora do dominio
    n = _um(con, "SELECT count(*) FROM silver_assinaturas WHERE plano = 'NAO_MAPEADO'")
    check("dominio_plano", "ERRO", n == 0, f"{n} assinaturas com plano fora do dominio conhecido", n)

    # -------------------------------------------- janela temporal
    n = _um(con, "SELECT count(*) FROM silver_faturas WHERE motivo_quarentena IS NULL "
                 "AND data_emissao > (SELECT data_corte FROM seed_parametros)")
    check("sem_documento_futuro", "ERRO", n == 0, f"{n} documentos emitidos depois da data de corte", n)

    # ================================================================ ALERTAS
    n = _um(con, "SELECT count(*) FROM alerta_pagamentos_orfaos")
    v = _um(con, "SELECT coalesce(sum(valor_brl), 0) FROM alerta_pagamentos_orfaos")
    check("pagamentos_orfaos", "ALERTA", n == 0,
          f"{n} pagamentos sem fatura correspondente, BRL {v:,.2f} em caixa nao reconciliado", v)

    v = _um(con, """
        WITH t AS (SELECT sum(custo_brl) tot FROM silver_infra_custos),
             s AS (SELECT sum(custo_brl) sem FROM silver_cogs_nao_atribuivel)
        SELECT (SELECT sem FROM s) / (SELECT tot FROM t)
    """)
    check("cogs_atribuivel", "ALERTA", v is not None and v < 0.05,
          f"{v:.1%} do COGS de cloud nao tem cliente identificado", v)

    n = _um(con, "SELECT count(*) FROM quarentena_assinaturas")
    check("quarentena_assinaturas", "ALERTA", n == 0, f"{n} assinaturas em quarentena", n)
    n = _um(con, "SELECT count(*) FROM quarentena_faturas")
    check("quarentena_faturas", "ALERTA", n == 0, f"{n} documentos em quarentena", n)
    n = _um(con, "SELECT count(*) FROM quarentena_clientes")
    check("quarentena_clientes", "ALERTA", n == 0, f"{n} clientes em quarentena", n)
    n = _um(con, "SELECT count(*) FROM silver_entidades WHERE cadastro_duplicado")
    check("cadastro_duplicado", "ALERTA", n == 0, f"{n} entidades com mais de um customer_id (mesmo CNPJ)", n)
    n = _um(con, "SELECT count(*) FROM silver_faturas WHERE bruto_menos_desconto_nao_fecha")
    check("aritmetica_documento", "ALERTA", n == 0,
          f"{n} documentos onde valor_bruto - desconto <> valor_liquido", n)
    n = _um(con, "SELECT count(*) FROM silver_assinaturas WHERE vigencia_invertida_na_origem")
    check("vigencia_reparada", "ALERTA", n == 0,
          f"{n} assinaturas tiveram end_date reparado pela regra de sucessao", n)

    log.info("checks: %d itens, %d falhas bloqueantes, %d alertas",
             len(rel.itens), len(rel.falhas_bloqueantes), len(rel.alertas))
    return rel
