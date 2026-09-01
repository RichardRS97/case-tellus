-- =====================================================================
-- 90_gold_unit_economics.sql
-- Pergunta 5: CAC por coorte e por canal, payback e LTV.
-- P10: PLG e Product-Led sao o mesmo canal; Brand nao tem cliente atribuivel
-- e entra somente no CAC blended.
-- P12: LTV sobre margem bruta e churn de receita, nao sobre receita bruta.
-- =====================================================================

-- Novos clientes por mes e canal, no grao de entidade economica (P08).
CREATE OR REPLACE TABLE gold_novos_clientes AS
SELECT
    strftime(e.signup_date, '%Y-%m')                    AS mes,
    e.canal,
    count(*)                                           AS novos_clientes
FROM silver_entidades e
WHERE e.signup_date IS NOT NULL
GROUP BY 1, 2;

-- CAC por canal e mes. Canais sem cliente atribuivel (Brand) ficam de fora do
-- numerador por canal e aparecem apenas no blended: dividir spend de marca por
-- zero cliente produziria CAC infinito.
CREATE OR REPLACE TABLE gold_cac_canal_mes AS
SELECT
    s.mes,
    s.canal,
    sum(s.spend_brl)                                   AS spend_brl,
    coalesce(n.novos_clientes, 0)                      AS novos_clientes,
    CASE WHEN coalesce(n.novos_clientes, 0) > 0
         THEN sum(s.spend_brl) / n.novos_clientes END  AS cac_brl,
    bool_or(s.canal_sem_atribuicao)                    AS canal_sem_atribuicao
FROM silver_marketing s
LEFT JOIN gold_novos_clientes n ON n.mes = s.mes AND n.canal = s.canal
JOIN seed_dim_mes d             ON d.mes = s.mes AND d.dentro_da_janela
GROUP BY 1, 2, n.novos_clientes
ORDER BY 1, 2;

-- CAC consolidado por canal no periodo inteiro (mais estavel que o mensal,
-- que oscila muito com meses de zero aquisicao).
CREATE OR REPLACE TABLE gold_cac_por_canal AS
WITH spend AS (
    SELECT s.canal, sum(s.spend_brl) AS spend_brl, bool_or(s.canal_sem_atribuicao) AS sem_atribuicao
    FROM silver_marketing s
    JOIN seed_dim_mes d ON d.mes = s.mes AND d.dentro_da_janela
    GROUP BY 1
),
novos AS (
    SELECT n.canal, sum(n.novos_clientes) AS novos_clientes
    FROM gold_novos_clientes n
    JOIN seed_dim_mes d ON d.mes = n.mes AND d.dentro_da_janela
    GROUP BY 1
)
SELECT
    s.canal,
    s.spend_brl,
    coalesce(n.novos_clientes, 0)                      AS novos_clientes,
    CASE WHEN coalesce(n.novos_clientes, 0) > 0 THEN s.spend_brl / n.novos_clientes END AS cac_brl,
    s.sem_atribuicao
FROM spend s
LEFT JOIN novos n USING (canal)
ORDER BY s.spend_brl DESC;

-- CAC blended: todo o investimento de aquisicao (inclusive Brand) sobre todos
-- os clientes adquiridos. E o numero que o board deve olhar, porque Brand
-- tambem foi pago.
CREATE OR REPLACE TABLE gold_cac_blended AS
WITH spend AS (
    SELECT sum(s.spend_brl) AS spend_total_brl,
           sum(s.spend_brl) FILTER (WHERE s.canal_sem_atribuicao) AS spend_sem_atribuicao_brl
    FROM silver_marketing s
    JOIN seed_dim_mes d ON d.mes = s.mes AND d.dentro_da_janela
),
novos AS (
    SELECT sum(n.novos_clientes) AS novos_clientes
    FROM gold_novos_clientes n
    JOIN seed_dim_mes d ON d.mes = n.mes AND d.dentro_da_janela
)
SELECT
    s.spend_total_brl,
    s.spend_sem_atribuicao_brl,
    s.spend_sem_atribuicao_brl / s.spend_total_brl     AS pct_spend_sem_atribuicao,
    n.novos_clientes,
    s.spend_total_brl / n.novos_clientes               AS cac_blended_brl,
    (s.spend_total_brl - s.spend_sem_atribuicao_brl) / n.novos_clientes AS cac_atribuivel_brl
FROM spend s CROSS JOIN novos n;

-- CAC por coorte de aquisicao (trimestre de signup), para ver se piorou.
CREATE OR REPLACE TABLE gold_cac_por_coorte AS
WITH coorte AS (
    SELECT
        left(n.mes, 4) || '-T' || cast(cast(floor((cast(substr(n.mes, 6, 2) AS INTEGER) - 1) / 3) + 1 AS INTEGER) AS VARCHAR) AS coorte,
        sum(n.novos_clientes) AS novos_clientes
    FROM gold_novos_clientes n
    JOIN seed_dim_mes d ON d.mes = n.mes AND d.dentro_da_janela
    GROUP BY 1
),
spend AS (
    SELECT
        left(s.mes, 4) || '-T' || cast(cast(floor((cast(substr(s.mes, 6, 2) AS INTEGER) - 1) / 3) + 1 AS INTEGER) AS VARCHAR) AS coorte,
        sum(s.spend_brl) AS spend_brl
    FROM silver_marketing s
    JOIN seed_dim_mes d ON d.mes = s.mes AND d.dentro_da_janela
    GROUP BY 1
)
SELECT
    c.coorte,
    s.spend_brl,
    c.novos_clientes,
    CASE WHEN c.novos_clientes > 0 THEN s.spend_brl / c.novos_clientes END AS cac_blended_brl
FROM coorte c JOIN spend s USING (coorte)
ORDER BY c.coorte;

-- =====================================================================
-- Payback e LTV. Usa medias do ultimo trimestre fechado da janela, para nao
-- deixar o indicador preso a um mes atipico.
-- =====================================================================
CREATE OR REPLACE TABLE gold_unit_economics AS
WITH janela AS (
    SELECT mes FROM seed_dim_mes WHERE dentro_da_janela ORDER BY ordem_mes DESC LIMIT 3
),
base AS (
    SELECT
        avg(m.arpa_brl)                             AS arpa_mensal_brl,
        avg(m.gross_revenue_churn)                  AS revenue_churn_mensal,
        avg(m.gross_churn_com_contracao)            AS revenue_churn_com_contracao,
        avg(m.nrr_mensal)                           AS nrr_mensal
    FROM gold_mrr_mensal m
    WHERE m.mes IN (SELECT mes FROM janela)
),
margem AS (
    SELECT
        avg(g.margem_direta_pct)                    AS gm_direta,
        avg(g.margem_consolidada_pct)               AS gm_consolidada
    FROM gold_margem_mensal g
    WHERE g.mes IN (SELECT mes FROM janela)
),
churn_logico AS (
    SELECT avg(c.logo_churn) AS logo_churn_mensal
    FROM gold_churn_mensal c WHERE c.mes IN (SELECT mes FROM janela)
)
SELECT
    b.arpa_mensal_brl,
    m.gm_direta,
    m.gm_consolidada,
    b.revenue_churn_mensal,
    b.revenue_churn_com_contracao,
    cl.logo_churn_mensal,
    cb.cac_blended_brl,
    cb.cac_atribuivel_brl,
    -- margem de contribuicao mensal por cliente
    b.arpa_mensal_brl * m.gm_direta                                     AS contribuicao_mensal_brl,
    -- P12: LTV correto usa margem bruta e churn de receita
    CASE WHEN b.revenue_churn_mensal > 0
         THEN b.arpa_mensal_brl * m.gm_direta / b.revenue_churn_mensal END AS ltv_brl,
    CASE WHEN b.revenue_churn_com_contracao > 0
         THEN b.arpa_mensal_brl * m.gm_direta / b.revenue_churn_com_contracao END AS ltv_conservador_brl,
    -- versao ingenua, mantida ao lado para evidenciar a diferenca de magnitude
    CASE WHEN cl.logo_churn_mensal > 0
         THEN b.arpa_mensal_brl / cl.logo_churn_mensal END              AS ltv_sem_margem_brl,
    CASE WHEN b.arpa_mensal_brl * m.gm_direta > 0
         THEN cb.cac_blended_brl / (b.arpa_mensal_brl * m.gm_direta) END AS payback_meses,
    CASE WHEN cb.cac_blended_brl > 0 AND b.revenue_churn_mensal > 0
         THEN (b.arpa_mensal_brl * m.gm_direta / b.revenue_churn_mensal) / cb.cac_blended_brl END AS ltv_cac
FROM base b CROSS JOIN margem m CROSS JOIN churn_logico cl CROSS JOIN gold_cac_blended cb;

-- Payback por canal: onde o capital de aquisicao volta mais rapido.
CREATE OR REPLACE TABLE gold_payback_por_canal AS
SELECT
    c.canal,
    c.cac_brl,
    c.novos_clientes,
    u.contribuicao_mensal_brl,
    CASE WHEN u.contribuicao_mensal_brl > 0 AND c.cac_brl IS NOT NULL
         THEN c.cac_brl / u.contribuicao_mensal_brl END                 AS payback_meses,
    CASE WHEN c.cac_brl > 0 THEN u.ltv_brl / c.cac_brl END              AS ltv_cac
FROM gold_cac_por_canal c CROSS JOIN gold_unit_economics u
WHERE NOT c.sem_atribuicao
ORDER BY payback_meses;


