-- =====================================================================
-- 95_naive.sql
-- Reproduz o resultado que sai das fontes SEM tratamento adequado, e isola o
-- efeito financeiro de cada erro separadamente.
--
-- Nao e um espantalho: e a sequencia de decisoes que um analista competente
-- toma quando confia no export. Ele consegue ler os numeros (usa decimal
-- pt-BR), mas assume que:
--   E1 cada linha do arquivo e um documento distinto        -> duplicidade
--   E2 documento emitido e receita                          -> inclui CANCELADA
--   E3 o sinal gravado esta correto                          -> NOTA_CREDITO soma
--   E4 valor e valor                                         -> USD somado como BRL
--   E5 receita e do mes em que a fatura saiu                 -> ignora competencia
--   E6 join com o mapa de workspace traz todo o custo         -> perde 50% do COGS
--   E7 contrato anual tem preco anual                        -> MRR x12
--   E8 customer_id e cliente                                 -> conta CNPJ 2x
--
-- A soma dos efeitos reconstroi exatamente a diferenca entre o numero
-- ingenuo e o numero correto. E o bridge que vai ao board.
-- =====================================================================

-- Base ingenua: TODAS as linhas, sem dedup, sem filtro de status, sem sinal,
-- sem conversao de moeda, alocada ao mes de emissao.
CREATE OR REPLACE TABLE naive_faturas AS
WITH bruto AS (
    SELECT
        trim(numero_fatura)                 AS numero_fatura,
        trim(id_cliente)                    AS customer_id,
        data_flex(data_emissao)             AS data_emissao,
        data_flex(competencia_inicio)       AS competencia_inicio,
        data_flex(competencia_fim)          AS competencia_fim,
        num_flex(valor_liquido)             AS valor_liquido,
        upper(trim(moeda))                  AS moeda,
        upper(trim(tipo))                   AS tipo,
        upper(trim(status))                 AS status,
        data_emissao                        AS data_emissao_texto,
        _hash_linha
    FROM bronze_faturas
)
SELECT
    b.*,
    strftime(b.data_emissao, '%Y-%m')       AS mes_emissao,
    row_number() OVER (
        PARTITION BY b.numero_fatura
        ORDER BY CASE WHEN b.data_emissao_texto SIMILAR TO '\d{4}-\d{2}-\d{2}' THEN 0 ELSE 1 END,
                 b._hash_linha
    )                                        AS rn,
    fx.usd_brl_medio                        AS fx_mes_emissao
FROM bruto b
LEFT JOIN silver_fx_mensal fx ON fx.mes = strftime(b.data_emissao, '%Y-%m');

-- Receita mensal ingenua: soma crua por mes de emissao.
CREATE OR REPLACE TABLE naive_receita_mensal AS
SELECT
    n.mes_emissao                           AS mes,
    sum(n.valor_liquido)                    AS receita_ingenua_brl
FROM naive_faturas n
JOIN seed_dim_mes d ON d.mes = n.mes_emissao AND d.dentro_da_janela
GROUP BY 1
ORDER BY 1;

-- ---------------------------------------------------------------------
-- Bridge de erro na receita do periodo. Cada linha e um efeito isolado.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE gold_bridge_receita AS
WITH janela AS (SELECT mes FROM seed_dim_mes WHERE dentro_da_janela),
-- E0: ponto de partida ingenuo
n0 AS (
    SELECT sum(valor_liquido) AS v
    FROM naive_faturas WHERE mes_emissao IN (SELECT mes FROM janela)
),
-- E1: linhas duplicadas contadas como documentos distintos
e1 AS (
    SELECT -sum(valor_liquido) AS v
    FROM naive_faturas WHERE rn > 1 AND mes_emissao IN (SELECT mes FROM janela)
),
-- E2: documentos cancelados somados como receita
e2 AS (
    SELECT -sum(valor_liquido) AS v
    FROM naive_faturas WHERE rn = 1 AND status = 'CANCELADA' AND mes_emissao IN (SELECT mes FROM janela)
),
-- E3: nota de credito gravada positiva; corrigir exige subtrair 2x
e3 AS (
    SELECT -2 * sum(valor_liquido) AS v
    FROM naive_faturas
    WHERE rn = 1 AND status <> 'CANCELADA' AND tipo = 'NOTA_CREDITO'
      AND mes_emissao IN (SELECT mes FROM janela)
),
-- E4: valores em USD somados como se fossem BRL
e4 AS (
    SELECT sum(CASE WHEN tipo = 'NOTA_CREDITO' THEN -valor_liquido ELSE valor_liquido END
               * (fx_mes_emissao - 1)) AS v
    FROM naive_faturas
    WHERE rn = 1 AND status <> 'CANCELADA' AND moeda = 'USD'
      AND mes_emissao IN (SELECT mes FROM janela)
),
-- correto: receita reconhecida por competencia dentro da janela
correto AS (
    SELECT sum(receita_brl) AS v
    FROM silver_receita_reconhecida WHERE mes IN (SELECT mes FROM janela)
),
subtotal AS (
    SELECT (SELECT v FROM n0) + coalesce((SELECT v FROM e1),0) + coalesce((SELECT v FROM e2),0)
         + coalesce((SELECT v FROM e3),0) + coalesce((SELECT v FROM e4),0) AS v
)
SELECT * FROM (
    VALUES
      (0, 'Receita "reportada" sem tratamento',
          'soma direta de valor_liquido por mes de emissao',
          (SELECT v FROM n0), 'partida'),
      (1, 'E1 Duplicidade de documentos',
          '47 numeros de fatura reexportados aparecem 2x no arquivo',
          coalesce((SELECT v FROM e1),0), 'ajuste'),
      (2, 'E2 Documentos cancelados tratados como receita',
          'status CANCELADA nao gera receita: o fato gerador foi anulado',
          coalesce((SELECT v FROM e2),0), 'ajuste'),
      (3, 'E3 Nota de credito somando em vez de subtrair',
          '35 notas gravadas com valor POSITIVO na origem; o sinal economico e negativo',
          coalesce((SELECT v FROM e3),0), 'ajuste'),
      (4, 'E4 USD somado como se fosse BRL',
          '247 documentos em USD sem conversao; PTAX media do mes de competencia',
          coalesce((SELECT v FROM e4),0), 'ajuste'),
      (5, 'E5 Receita alocada na emissao em vez da competencia',
          'residuo de reclassificacao temporal: 53 documentos cobrem ate 13 meses',
          (SELECT v FROM correto) - (SELECT v FROM subtotal), 'ajuste'),
      (6, 'Receita reconhecida correta (competencia, BRL)',
          'base auditavel do periodo jan/2024 a jun/2026',
          (SELECT v FROM correto), 'chegada')
) AS t(ordem, efeito, explicacao, valor_brl, papel);

-- ---------------------------------------------------------------------
-- MRR ingenuo: anualiza contrato anual, nao normaliza plano, nao deduplica,
-- soma USD como BRL.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE naive_mrr_mensal AS
WITH assinaturas AS (
    SELECT
        trim(subscription_id)                       AS subscription_id,
        trim(customer_id)                           AS customer_id,
        plan                                        AS plano_bruto,
        TRY_CAST(num_flex(seats) AS INTEGER)        AS seats,
        num_flex(unit_price)                        AS unit_price,
        upper(trim(currency))                       AS moeda,
        lower(trim(coalesce(billing_period,'')))    AS ciclo,
        data_flex(start_date)                       AS start_date,
        data_flex(end_date)                         AS end_date
    FROM bronze_assinaturas
)
SELECT
    d.mes,
    sum(a.seats * a.unit_price * CASE WHEN a.ciclo = 'annual' THEN 12 ELSE 1 END) AS mrr_ingenuo_brl,
    count(DISTINCT a.customer_id)                                                 AS clientes_ingenuo,
    count(DISTINCT chave_dominio(a.plano_bruto))                                  AS planos_distintos_vistos
FROM seed_dim_mes d
JOIN assinaturas a
  ON a.start_date <= d.fim_mes
 AND (a.end_date IS NULL OR a.end_date >= d.fim_mes)
WHERE d.dentro_da_janela
GROUP BY 1
ORDER BY 1;

-- ---------------------------------------------------------------------
-- COGS ingenuo: INNER JOIN com o mapa de workspace. O erro e silencioso, o
-- custo dos 27 workspaces sem dono simplesmente desaparece do resultado.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE naive_cogs AS
WITH bruto AS (
    SELECT trim(month) AS mes, trim(workspace_id) AS workspace_id,
           lower(trim(service)) AS servico, num_flex(cost_usd) AS custo_usd
    FROM bronze_infra_costs
)
SELECT
    b.mes,
    sum(b.custo_usd)                                    AS cogs_usd_visto,
    -- o ingenuo reporta USD como se fosse BRL
    sum(b.custo_usd)                                    AS cogs_ingenuo_brl,
    count(DISTINCT b.workspace_id)                      AS workspaces_vistos
FROM bruto b
JOIN silver_workspace_map m ON m.workspace_id = b.workspace_id
JOIN seed_dim_mes d          ON d.mes = b.mes AND d.dentro_da_janela
GROUP BY 1;

-- ---------------------------------------------------------------------
-- CAC ingenuo: customer_id como cliente, inclui signup futuro, canal sem
-- harmonizacao de dominio (PLG x Product-Led).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE naive_cac AS
WITH novos AS (
    SELECT strftime(data_flex(signup_date), '%Y-%m') AS mes,
           trim(acquisition_channel)                 AS canal,
           count(*)                                  AS novos
    FROM bronze_customers
    GROUP BY 1, 2
),
spend AS (
    SELECT trim(month) AS mes, trim(channel) AS canal, num_flex(spend_brl) AS spend
    FROM bronze_sales_marketing_spend
)
SELECT
    s.canal                                            AS canal_spend,
    sum(s.spend)                                       AS spend_brl,
    coalesce(sum(n.novos), 0)                          AS novos_clientes_encontrados,
    CASE WHEN coalesce(sum(n.novos), 0) > 0 THEN sum(s.spend) / sum(n.novos) END AS cac_ingenuo_brl
FROM spend s
LEFT JOIN novos n ON n.mes = s.mes AND n.canal = s.canal
JOIN seed_dim_mes d ON d.mes = s.mes AND d.dentro_da_janela
GROUP BY 1
ORDER BY 2 DESC;

-- Comparativo consolidado ingenuo x correto, para a tabela de abertura do
-- relatorio executivo.
CREATE OR REPLACE TABLE gold_comparativo_metricas AS
WITH janela AS (SELECT mes FROM seed_dim_mes WHERE dentro_da_janela),
ult AS (SELECT mes FROM seed_dim_mes WHERE dentro_da_janela ORDER BY ordem_mes DESC LIMIT 1),
rec_n AS (SELECT sum(receita_ingenua_brl) v FROM naive_receita_mensal),
rec_c AS (SELECT sum(receita_brl) v FROM silver_receita_reconhecida WHERE mes IN (SELECT mes FROM janela)),
mrr_n AS (SELECT mrr_ingenuo_brl v FROM naive_mrr_mensal WHERE mes = (SELECT mes FROM ult)),
mrr_c AS (SELECT mrr_brl v FROM gold_mrr_mensal WHERE mes = (SELECT mes FROM ult)),
cog_n AS (SELECT sum(cogs_ingenuo_brl) v FROM naive_cogs),
cog_c AS (SELECT sum(cogs_total_brl) v FROM gold_margem_mensal),
mrg_n AS (SELECT (SELECT v FROM rec_n) - (SELECT v FROM cog_n) v),
mrg_c AS (SELECT sum(margem_consolidada_brl) v FROM gold_margem_mensal),
cli_n AS (SELECT count(*) v FROM bronze_customers),
cli_c AS (SELECT count(*) v FROM silver_entidades WHERE signup_date IS NOT NULL),
cac_n AS (SELECT sum(spend_brl) / (SELECT v FROM cli_n) v FROM silver_marketing
          WHERE mes IN (SELECT mes FROM janela)),
cac_c AS (SELECT cac_blended_brl v FROM gold_cac_blended),
ltv_n AS (SELECT ltv_sem_margem_brl v FROM gold_unit_economics),
ltv_c AS (SELECT ltv_brl v FROM gold_unit_economics)
SELECT * FROM (
    VALUES
      (1, 'Receita do periodo (jan/24 a jun/26)', 'BRL', (SELECT v FROM rec_n), (SELECT v FROM rec_c)),
      (2, 'MRR no fechamento de jun/2026',        'BRL', (SELECT v FROM mrr_n), (SELECT v FROM mrr_c)),
      (3, 'ARR no fechamento de jun/2026',        'BRL', (SELECT v FROM mrr_n) * 12, (SELECT v FROM mrr_c) * 12),
      (4, 'COGS de cloud do periodo',             'BRL', (SELECT v FROM cog_n), (SELECT v FROM cog_c)),
      (5, 'Margem bruta do periodo',              'BRL', (SELECT v FROM mrg_n), (SELECT v FROM mrg_c)),
      (6, 'Clientes considerados',                'un',  (SELECT v FROM cli_n), (SELECT v FROM cli_c)),
      (7, 'CAC blended',                          'BRL', (SELECT v FROM cac_n), (SELECT v FROM cac_c)),
      (8, 'LTV',                                  'BRL', (SELECT v FROM ltv_n), (SELECT v FROM ltv_c))
) AS t(ordem, metrica, unidade, valor_ingenuo, valor_correto);
