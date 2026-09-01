-- =====================================================================
-- 80_gold_margem.sql
-- Pergunta 4: margem bruta por mes, por plano e por cliente.
-- P09: o COGS nao atribuivel (50,6% do custo) nao e rateado no numero
-- principal. A margem e reportada em duas camadas explicitas.
-- =====================================================================

-- COGS por entidade e mes, somando os workspaces daquela entidade.
-- O join workspace -> cliente e N:1, portanto agregamos ANTES de juntar com
-- receita: juntar primeiro duplicaria a receita pelo numero de workspaces.
CREATE OR REPLACE TABLE gold_cogs_entidade_mes AS
SELECT
    i.mes,
    i.entidade_id,
    sum(i.custo_usd)                                                      AS cogs_usd,
    sum(i.custo_brl)                                                      AS cogs_brl,
    sum(i.custo_brl) FILTER (WHERE i.servico = 'compute')                 AS cogs_compute_brl,
    sum(i.custo_brl) FILTER (WHERE i.servico = 'storage')                 AS cogs_storage_brl,
    sum(i.custo_brl) FILTER (WHERE i.servico = 'egress')                  AS cogs_egress_brl,
    sum(i.custo_brl) FILTER (WHERE i.servico = 'ai_tokens')               AS cogs_ai_tokens_brl,
    count(DISTINCT i.workspace_id)                                        AS workspaces
FROM silver_infra_custos i
WHERE NOT i.sem_dono
GROUP BY 1, 2;

-- Receita por entidade e mes (reconhecida, ja em BRL).
CREATE OR REPLACE TABLE gold_receita_entidade_mes AS
SELECT
    r.mes,
    r.entidade_id,
    sum(r.receita_brl)                                                    AS receita_brl,
    sum(r.receita_brl) FILTER (WHERE r.tipo = 'NOTA_CREDITO')             AS notas_credito_brl
FROM silver_receita_reconhecida r
WHERE r.entidade_id IS NOT NULL
GROUP BY 1, 2;

-- Margem consolidada por mes, com as duas camadas de COGS lado a lado.
CREATE OR REPLACE TABLE gold_margem_mensal AS
WITH atribuivel AS (
    SELECT mes, sum(cogs_brl) AS cogs_atribuivel_brl FROM gold_cogs_entidade_mes GROUP BY 1
),
nao_atribuivel AS (
    SELECT mes, sum(custo_brl) AS cogs_nao_atribuivel_brl FROM silver_cogs_nao_atribuivel GROUP BY 1
)
SELECT
    d.mes,
    coalesce(r.receita_reconhecida_brl, 0)                                AS receita_brl,
    coalesce(a.cogs_atribuivel_brl, 0)                                    AS cogs_atribuivel_brl,
    coalesce(n.cogs_nao_atribuivel_brl, 0)                                AS cogs_nao_atribuivel_brl,
    coalesce(a.cogs_atribuivel_brl, 0) + coalesce(n.cogs_nao_atribuivel_brl, 0) AS cogs_total_brl,
    -- camada 1: margem direta, so o custo com dono identificado
    coalesce(r.receita_reconhecida_brl, 0) - coalesce(a.cogs_atribuivel_brl, 0) AS margem_direta_brl,
    CASE WHEN coalesce(r.receita_reconhecida_brl, 0) > 0
         THEN 1 - coalesce(a.cogs_atribuivel_brl, 0) / r.receita_reconhecida_brl END AS margem_direta_pct,
    -- camada 2: margem consolidada, todo o custo de servir
    coalesce(r.receita_reconhecida_brl, 0)
      - coalesce(a.cogs_atribuivel_brl, 0) - coalesce(n.cogs_nao_atribuivel_brl, 0) AS margem_consolidada_brl,
    CASE WHEN coalesce(r.receita_reconhecida_brl, 0) > 0
         THEN 1 - (coalesce(a.cogs_atribuivel_brl, 0) + coalesce(n.cogs_nao_atribuivel_brl, 0))
                  / r.receita_reconhecida_brl END                          AS margem_consolidada_pct
FROM seed_dim_mes d
LEFT JOIN gold_receita_mensal r ON r.mes = d.mes
LEFT JOIN atribuivel          a ON a.mes = d.mes
LEFT JOIN nao_atribuivel      n ON n.mes = d.mes
WHERE d.dentro_da_janela
ORDER BY d.mes;

-- Margem por plano. O plano do mes vem do MRR vigente, nao da fatura, porque
-- a fatura de um contrato anual carrega competencia de varios meses.
CREATE OR REPLACE TABLE gold_margem_por_plano AS
SELECT
    m.plano_principal                                                     AS plano,
    sum(coalesce(r.receita_brl, 0))                                       AS receita_brl,
    sum(coalesce(c.cogs_brl, 0))                                          AS cogs_atribuivel_brl,
    sum(coalesce(r.receita_brl, 0)) - sum(coalesce(c.cogs_brl, 0))         AS margem_direta_brl,
    CASE WHEN sum(coalesce(r.receita_brl, 0)) > 0
         THEN 1 - sum(coalesce(c.cogs_brl, 0)) / sum(coalesce(r.receita_brl, 0)) END AS margem_direta_pct,
    count(DISTINCT m.entidade_id)                                         AS entidades,
    sum(m.mrr_brl)                                                        AS mrr_acumulado_brl
FROM gold_mrr_entidade_mes m
JOIN seed_dim_mes d              ON d.mes = m.mes AND d.dentro_da_janela
LEFT JOIN gold_receita_entidade_mes r ON r.mes = m.mes AND r.entidade_id = m.entidade_id
LEFT JOIN gold_cogs_entidade_mes    c ON c.mes = m.mes AND c.entidade_id = m.entidade_id
GROUP BY 1
ORDER BY margem_direta_brl DESC;

-- Visao por cliente: quem da e quem nao da lucro. Entregavel 3 do enunciado.
CREATE OR REPLACE TABLE gold_margem_por_cliente AS
WITH receita AS (
    SELECT r.entidade_id, sum(r.receita_brl) AS receita_brl
    FROM gold_receita_entidade_mes r
    JOIN seed_dim_mes d ON d.mes = r.mes AND d.dentro_da_janela
    GROUP BY 1
),
cogs AS (
    SELECT c.entidade_id, sum(c.cogs_brl) AS cogs_brl, max(c.workspaces) AS workspaces
    FROM gold_cogs_entidade_mes c
    JOIN seed_dim_mes d ON d.mes = c.mes AND d.dentro_da_janela
    GROUP BY 1
),
mrr_atual AS (
    SELECT g.entidade_id, g.mrr_brl, g.plano_principal, g.moeda
    FROM gold_mrr_grade g
    WHERE g.mes = (SELECT mes FROM seed_dim_mes WHERE dentro_da_janela ORDER BY ordem_mes DESC LIMIT 1)
)
SELECT
    e.entidade_id,
    e.nome_fantasia,
    e.pais,
    e.segmento,
    e.canal,
    e.signup_date,
    e.cadastro_duplicado,
    coalesce(ma.plano_principal, 'sem assinatura vigente')                AS plano_atual,
    coalesce(ma.mrr_brl, 0)                                               AS mrr_atual_brl,
    coalesce(r.receita_brl, 0)                                            AS receita_periodo_brl,
    coalesce(c.cogs_brl, 0)                                               AS cogs_atribuivel_brl,
    coalesce(r.receita_brl, 0) - coalesce(c.cogs_brl, 0)                   AS margem_direta_brl,
    CASE WHEN coalesce(r.receita_brl, 0) > 0
         THEN 1 - coalesce(c.cogs_brl, 0) / r.receita_brl END              AS margem_direta_pct,
    coalesce(c.workspaces, 0)                                             AS workspaces,
    c.entidade_id IS NULL                                                 AS sem_custo_atribuido,
    coalesce(r.receita_brl, 0) - coalesce(c.cogs_brl, 0) < 0              AS destroi_valor
FROM silver_entidades e
LEFT JOIN receita   r  ON r.entidade_id  = e.entidade_id
LEFT JOIN cogs      c  ON c.entidade_id  = e.entidade_id
LEFT JOIN mrr_atual ma ON ma.entidade_id = e.entidade_id
ORDER BY margem_direta_brl ASC;
