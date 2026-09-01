-- =====================================================================
-- 60_gold_receita_caixa.sql
-- Pergunta 1: receita reconhecida x receita em caixa x receita diferida.
-- =====================================================================

-- Receita reconhecida por mes, na moeda de reporte, com abertura de origem.
CREATE OR REPLACE TABLE gold_receita_mensal AS
SELECT
    r.mes,
    sum(r.receita_brl)                                                  AS receita_reconhecida_brl,
    sum(CASE WHEN r.moeda = 'BRL' THEN r.receita_brl ELSE 0 END)        AS receita_brl_origem_brl,
    sum(CASE WHEN r.moeda = 'USD' THEN r.receita_brl ELSE 0 END)        AS receita_brl_origem_usd,
    sum(CASE WHEN r.tipo = 'NOTA_CREDITO' THEN r.receita_brl ELSE 0 END) AS notas_credito_brl,
    sum(CASE WHEN r.dias_competencia > 62 THEN r.receita_brl ELSE 0 END) AS receita_de_contratos_longos_brl,
    count(DISTINCT r.numero_fatura)                                     AS documentos,
    count(DISTINCT r.entidade_id)                                       AS entidades_faturadas
FROM silver_receita_reconhecida r
GROUP BY 1;

-- Caixa por mes de liquidacao.
CREATE OR REPLACE TABLE gold_caixa_mensal AS
SELECT
    p.mes_caixa                                                         AS mes,
    sum(p.valor_brl)                                                    AS caixa_liquido_brl,
    sum(CASE WHEN NOT p.eh_reembolso THEN p.valor_brl ELSE 0 END)        AS recebimentos_brl,
    sum(CASE WHEN p.eh_reembolso     THEN p.valor_brl ELSE 0 END)        AS reembolsos_brl,
    sum(CASE WHEN NOT p.reconciliado_com_fatura THEN p.valor_brl ELSE 0 END) AS caixa_nao_reconciliado_brl,
    count(*)                                                            AS pagamentos
FROM silver_pagamentos p
WHERE p.motivo_quarentena IS NULL
GROUP BY 1;

-- Confronto lado a lado. A diferenca entre as duas colunas e a pergunta 1.
CREATE OR REPLACE TABLE gold_receita_vs_caixa AS
SELECT
    m.mes,
    coalesce(r.receita_reconhecida_brl, 0)                              AS receita_reconhecida_brl,
    coalesce(c.caixa_liquido_brl, 0)                                    AS caixa_liquido_brl,
    coalesce(c.caixa_liquido_brl, 0) - coalesce(r.receita_reconhecida_brl, 0) AS diferenca_brl,
    coalesce(c.caixa_nao_reconciliado_brl, 0)                           AS caixa_nao_reconciliado_brl,
    coalesce(r.receita_de_contratos_longos_brl, 0)                       AS receita_de_contratos_longos_brl,
    coalesce(r.notas_credito_brl, 0)                                    AS notas_credito_brl
FROM seed_dim_mes m
LEFT JOIN gold_receita_mensal r ON r.mes = m.mes
LEFT JOIN gold_caixa_mensal   c ON c.mes = m.mes
WHERE m.dentro_da_janela
ORDER BY m.mes;

-- Saldo de receita diferida no fechamento de junho/2026: quanto ja foi
-- faturado e ainda nao foi entregue.
CREATE OR REPLACE TABLE gold_receita_diferida_fechamento AS
SELECT
    count(DISTINCT numero_fatura)       AS documentos_com_saldo,
    count(DISTINCT entidade_id)         AS entidades,
    sum(receita_diferida_brl)           AS saldo_diferido_brl,
    min(primeiro_mes_futuro)            AS primeiro_mes,
    max(ultimo_mes_futuro)              AS ultimo_mes
FROM silver_receita_diferida;

CREATE OR REPLACE TABLE gold_receita_diferida_por_mes_futuro AS
SELECT r.mes, sum(r.receita_brl) AS receita_a_reconhecer_brl
FROM silver_receita_reconhecida r
WHERE r.mes > strftime((SELECT periodo_fim FROM seed_parametros), '%Y-%m')
GROUP BY 1
ORDER BY 1;
