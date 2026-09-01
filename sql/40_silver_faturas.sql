-- =====================================================================
-- 40_silver_faturas.sql
-- Concentra P01, P02, P03 e P05. E a tabela onde a receita e definida.
-- =====================================================================

CREATE OR REPLACE TABLE silver_faturas AS
WITH bruto AS (
    SELECT
        trim(numero_fatura)                         AS numero_fatura,
        trim(id_cliente)                            AS customer_id,
        trim(cliente_nome)                          AS cliente_nome,
        trim(id_assinatura)                         AS subscription_id,
        data_flex(data_emissao)                     AS data_emissao,
        data_flex(competencia_inicio)               AS competencia_inicio,
        data_flex(competencia_fim)                  AS competencia_fim,
        num_flex(valor_bruto)                       AS valor_bruto,
        num_flex(desconto)                          AS desconto,
        num_flex(valor_liquido)                     AS valor_liquido,
        upper(trim(moeda))                          AS moeda,
        upper(trim(tipo))                           AS tipo,
        upper(trim(status))                         AS status,
        data_emissao                                AS data_emissao_texto,
        _linha_fisica,
        _hash_linha
    FROM bronze_faturas
),
-- P05: 47 numeros de fatura aparecem 2x. Confirmado que cliente, valor, moeda
-- e tipo sao identicos e apenas o formato da data difere: e reexportacao do
-- mesmo documento. A ordenacao de desempate e deterministica (ISO primeiro),
-- garantindo que duas execucoes escolham exatamente a mesma linha.
dedup AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY numero_fatura
            ORDER BY CASE WHEN data_emissao_texto SIMILAR TO '\d{4}-\d{2}-\d{2}' THEN 0 ELSE 1 END,
                     _hash_linha
        ) AS rn,
        count(*) OVER (PARTITION BY numero_fatura) AS copias
    FROM bruto
)
SELECT
    d.numero_fatura,
    d.customer_id,
    cl.entidade_id,
    d.cliente_nome,
    d.subscription_id,
    d.data_emissao,
    d.competencia_inicio,
    d.competencia_fim,
    d.valor_bruto,
    d.desconto,
    d.valor_liquido,
    d.moeda,
    d.tipo,
    d.status,
    d.copias                                        AS copias_na_origem,
    d.copias > 1                                    AS veio_duplicada,
    -- P02: nota de credito esta gravada com valor POSITIVO na origem.
    -- O sinal economico e negativo: e devolucao de receita.
    CASE WHEN d.tipo = 'NOTA_CREDITO' THEN -1 ELSE 1 END AS sinal,
    CASE WHEN d.tipo = 'NOTA_CREDITO' THEN -d.valor_liquido ELSE d.valor_liquido END
                                                    AS valor_com_sinal,
    -- P02: cancelada nao gera receita; aberta e vencida geram (fato ocorrido)
    d.status <> 'CANCELADA'                          AS elegivel_receita,
    -- coerencia aritmetica do proprio documento
    abs(coalesce(d.valor_bruto, 0) - coalesce(d.desconto, 0) - coalesce(d.valor_liquido, 0)) > 0.01
                                                    AS bruto_menos_desconto_nao_fecha,
    datediff('day', d.competencia_inicio, d.competencia_fim) + 1 AS dias_competencia,
    CASE
        WHEN d.valor_liquido IS NULL                              THEN 'valor_liquido ilegivel'
        WHEN d.competencia_inicio IS NULL OR d.competencia_fim IS NULL
                                                                  THEN 'competencia ilegivel'
        WHEN d.competencia_fim < d.competencia_inicio             THEN 'competencia invertida'
        WHEN d.moeda NOT IN ('BRL', 'USD')                        THEN 'moeda desconhecida'
        WHEN d.data_emissao > (SELECT data_corte FROM seed_parametros)
                                                                  THEN 'emissao posterior a data de corte'
    END                                             AS motivo_quarentena
FROM dedup d
LEFT JOIN silver_clientes cl ON cl.customer_id = d.customer_id
WHERE d.rn = 1;

CREATE OR REPLACE TABLE quarentena_faturas AS
SELECT numero_fatura, customer_id, tipo, status, moeda, valor_liquido,
       competencia_inicio, competencia_fim, motivo_quarentena
FROM silver_faturas
WHERE motivo_quarentena IS NOT NULL;

-- =====================================================================
-- Receita reconhecida: rateio pro-rata DIARIO sobre o periodo de competencia.
-- P01. Este e o coracao da diferenca entre o numero ingenuo e o numero certo:
-- 53 documentos cobrem mais de 2 meses, ate 13 meses de competencia.
-- =====================================================================
CREATE OR REPLACE TABLE silver_receita_reconhecida AS
WITH elegiveis AS (
    SELECT *
    FROM silver_faturas
    WHERE motivo_quarentena IS NULL
      AND elegivel_receita
),
meses AS (
    SELECT
        e.*,
        unnest(generate_series(
            date_trunc('month', e.competencia_inicio),
            date_trunc('month', e.competencia_fim),
            INTERVAL 1 MONTH
        ))::DATE AS mes_ref
    FROM elegiveis e
),
rateio AS (
    SELECT
        m.numero_fatura,
        m.customer_id,
        m.entidade_id,
        m.subscription_id,
        m.tipo,
        m.status,
        m.moeda,
        m.data_emissao,
        m.competencia_inicio,
        m.competencia_fim,
        m.dias_competencia,
        strftime(m.mes_ref, '%Y-%m')                            AS mes,
        greatest(m.competencia_inicio, m.mes_ref)               AS ini_no_mes,
        least(m.competencia_fim, (m.mes_ref + INTERVAL 1 MONTH - INTERVAL 1 DAY)::DATE) AS fim_no_mes,
        m.valor_com_sinal
    FROM meses m
),
com_dias AS (
    SELECT *, datediff('day', ini_no_mes, fim_no_mes) + 1 AS dias_no_mes
    FROM rateio
    WHERE fim_no_mes >= ini_no_mes
)
SELECT
    c.numero_fatura,
    c.customer_id,
    c.entidade_id,
    c.subscription_id,
    c.tipo,
    c.status,
    c.moeda,
    c.mes,
    c.data_emissao,
    c.competencia_inicio,
    c.competencia_fim,
    c.dias_competencia,
    c.dias_no_mes,
    c.dias_no_mes::DOUBLE / c.dias_competencia              AS fracao_do_documento,
    c.valor_com_sinal                                       AS valor_documento_moeda_origem,
    c.valor_com_sinal * c.dias_no_mes / c.dias_competencia   AS receita_moeda_origem,
    -- P03: fluxo de competencia convertido pela PTAX media do mes de competencia
    fx.usd_brl_medio                                        AS usd_brl_aplicado,
    CASE
        WHEN c.moeda = 'BRL' THEN c.valor_com_sinal * c.dias_no_mes / c.dias_competencia
        ELSE c.valor_com_sinal * c.dias_no_mes / c.dias_competencia * fx.usd_brl_medio
    END                                                     AS receita_brl
FROM com_dias c
LEFT JOIN silver_fx_mensal fx ON fx.mes = c.mes;

-- =====================================================================
-- Receita diferida: parcela ja faturada cuja competencia e posterior ao
-- fechamento da janela de analise (30/06/2026).
-- =====================================================================
CREATE OR REPLACE TABLE silver_receita_diferida AS
SELECT
    r.numero_fatura,
    r.customer_id,
    r.entidade_id,
    r.moeda,
    r.competencia_inicio,
    r.competencia_fim,
    sum(r.receita_brl)                                      AS receita_diferida_brl,
    min(r.mes)                                              AS primeiro_mes_futuro,
    max(r.mes)                                              AS ultimo_mes_futuro
FROM silver_receita_reconhecida r
WHERE r.mes > strftime((SELECT periodo_fim FROM seed_parametros), '%Y-%m')
GROUP BY 1, 2, 3, 4, 5, 6;
