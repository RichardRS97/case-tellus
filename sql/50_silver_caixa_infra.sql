-- =====================================================================
-- 50_silver_caixa_infra.sql
-- Pagamentos (P04) e custo de cloud (P09).
-- =====================================================================

CREATE OR REPLACE TABLE silver_pagamentos AS
WITH bruto AS (
    SELECT
        trim(payment_id)                    AS payment_id,
        trim(numero_fatura)                 AS numero_fatura,
        data_flex(paid_at)                  AS paid_at,
        num_flex(amount)                    AS valor_moeda_origem,
        upper(trim(currency))               AS moeda,
        lower(trim(method))                 AS metodo,
        _hash_linha
    FROM bronze_payments
)
SELECT
    b.payment_id,
    b.numero_fatura,
    b.paid_at,
    strftime(b.paid_at, '%Y-%m')            AS mes_caixa,
    b.valor_moeda_origem,
    b.moeda,
    b.metodo,
    b.valor_moeda_origem < 0                AS eh_reembolso,
    f.numero_fatura IS NOT NULL             AS reconciliado_com_fatura,
    f.customer_id,
    f.entidade_id,
    f.tipo                                  AS tipo_documento,
    f.status                                AS status_documento,
    -- P04: caixa e evento datado, converte pela PTAX do dia da liquidacao
    -- com forward-fill para fim de semana e feriado.
    fx.usd_brl                              AS usd_brl_aplicado,
    fx.taxa_por_forward_fill,
    CASE WHEN b.moeda = 'BRL' THEN b.valor_moeda_origem
         ELSE b.valor_moeda_origem * fx.usd_brl END AS valor_brl,
    CASE
        WHEN b.paid_at IS NULL                                      THEN 'paid_at ilegivel'
        WHEN b.valor_moeda_origem IS NULL                           THEN 'amount ilegivel'
        WHEN b.moeda NOT IN ('BRL','USD')                           THEN 'moeda desconhecida'
        WHEN b.paid_at > (SELECT data_corte FROM seed_parametros)    THEN 'pagamento posterior a data de corte'
        WHEN b.moeda = 'USD' AND fx.usd_brl IS NULL                 THEN 'sem cotacao para a data'
    END                                     AS motivo_quarentena
FROM bruto b
LEFT JOIN silver_faturas  f  ON f.numero_fatura = b.numero_fatura
LEFT JOIN silver_fx_diario fx ON fx.data = b.paid_at;

CREATE OR REPLACE TABLE quarentena_pagamentos AS
SELECT payment_id, numero_fatura, paid_at, valor_moeda_origem, moeda, motivo_quarentena
FROM silver_pagamentos WHERE motivo_quarentena IS NOT NULL;

-- Pagamentos sem fatura correspondente: nao entram em receita, mas entram em
-- caixa. Isolados porque sao exatamente o tipo de item que quebra reconciliacao
-- entre financeiro e contabil.
CREATE OR REPLACE TABLE alerta_pagamentos_orfaos AS
SELECT payment_id, numero_fatura, paid_at, valor_brl, moeda, metodo
FROM silver_pagamentos
WHERE motivo_quarentena IS NULL AND NOT reconciliado_com_fatura;

-- =====================================================================
-- Custo de cloud. Grao de origem: (mes, workspace, servico) em USD.
-- =====================================================================
-- O mapa de workspace tem dois defeitos distintos, tratados de forma distinta:
--   (a) 3 pares (workspace, cliente) repetidos identicos -> DISTINCT resolve;
--   (b) 3 workspaces apontando para DOIS clientes diferentes, com CNPJ e razao
--       social distintos (ws-0043, ws-0053, ws-0056; USD 51 mil de custo).
-- O caso (b) nao e duplicidade, e conflito de atribuicao. Escolher um dono seria
-- arbitrario e manter os dois duplicaria o custo no fan-out do join. Marcamos
-- como ambiguo e o custo vai para o bucket nao atribuivel (P15).
CREATE OR REPLACE TABLE silver_workspace_map AS
WITH distinto AS (
    SELECT DISTINCT trim(workspace_id) AS workspace_id, trim(customer_id) AS customer_id
    FROM bronze_workspace_map
),
contagem AS (
    SELECT workspace_id, count(*) AS donos FROM distinto GROUP BY 1
)
SELECT
    d.workspace_id,
    CASE WHEN c.donos > 1 THEN NULL ELSE d.customer_id END AS customer_id,
    c.donos > 1                                            AS mapeamento_ambiguo,
    c.donos                                                AS donos_declarados
FROM distinto d
JOIN contagem c USING (workspace_id)
QUALIFY row_number() OVER (PARTITION BY d.workspace_id ORDER BY d.customer_id) = 1;


CREATE OR REPLACE TABLE silver_infra_custos AS
WITH bruto AS (
    SELECT
        trim(month)                 AS mes,
        trim(workspace_id)          AS workspace_id,
        lower(trim(service))        AS servico,
        num_flex(cost_usd)          AS custo_usd,
        _hash_linha
    FROM bronze_infra_costs
),
-- 4 chaves (mes, workspace, servico) vem duplicadas com valor identico.
-- Mesmo tratamento das faturas: e reexportacao, nao custo em dobro.
dedup AS (
    SELECT *,
        row_number() OVER (PARTITION BY mes, workspace_id, servico ORDER BY _hash_linha) AS rn,
        count(*)     OVER (PARTITION BY mes, workspace_id, servico)                      AS copias
    FROM bruto
)
SELECT
    d.mes,
    d.workspace_id,
    d.servico,
    d.custo_usd,
    d.copias > 1                        AS veio_duplicada,
    d.custo_usd < 0                     AS eh_credito_cloud,
    m.customer_id,
    cl.entidade_id,
    m.customer_id IS NULL               AS sem_dono,
    coalesce(m.mapeamento_ambiguo, FALSE) AS mapeamento_ambiguo,
    CASE
        WHEN m.workspace_id IS NULL           THEN 'workspace ausente do mapa'
        WHEN coalesce(m.mapeamento_ambiguo, FALSE) THEN 'workspace com mais de um cliente declarado'
    END                                 AS motivo_nao_atribuivel,
    fx.usd_brl_medio                    AS usd_brl_aplicado,
    d.custo_usd * fx.usd_brl_medio      AS custo_brl
FROM dedup d
LEFT JOIN silver_workspace_map m  ON m.workspace_id = d.workspace_id
LEFT JOIN silver_clientes      cl ON cl.customer_id = m.customer_id
LEFT JOIN silver_fx_mensal     fx ON fx.mes = d.mes
WHERE d.rn = 1;

-- P09 e P15: COGS sem dono identificavel, com o motivo separado. Mantido em
-- tabela propria e visivel no relatorio, nunca rateado por receita para
-- "fechar" a margem por cliente.
CREATE OR REPLACE TABLE silver_cogs_nao_atribuivel AS
SELECT
    mes,
    workspace_id,
    coalesce(motivo_nao_atribuivel, 'nao classificado') AS motivo,
    sum(custo_usd) AS custo_usd,
    sum(custo_brl) AS custo_brl
FROM silver_infra_custos
WHERE sem_dono
GROUP BY 1, 2, 3;

-- =====================================================================
-- Investimento de aquisicao. P10: dominio de canal divergente entre as fontes.
-- =====================================================================
CREATE OR REPLACE TABLE silver_marketing AS
SELECT
    trim(s.month)                                       AS mes,
    coalesce(m.canal_padrao, trim(s.channel))           AS canal,
    trim(s.channel)                                     AS canal_origem,
    num_flex(s.spend_brl)                               AS spend_brl,
    coalesce(m.canal_padrao, trim(s.channel)) IN (SELECT canal FROM seed_canal_sem_atribuicao)
                                                        AS canal_sem_atribuicao
FROM bronze_sales_marketing_spend s
LEFT JOIN seed_mapa_canal m ON chave_dominio(s.channel) = m.canal_bruto;
