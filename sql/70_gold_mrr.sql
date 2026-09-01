-- =====================================================================
-- 70_gold_mrr.sql
-- Perguntas 2 e 3: MRR, ARR, decomposicao da variacao, NRR e churn.
--
-- Decisao central: a decomposicao usa uma identidade algebrica exata que
-- separa efeito de volume de efeito cambial.
--
--   MRR_t*FX_t - MRR_(t-1)*FX_(t-1)
--     = (MRR_t - MRR_(t-1)) * FX_(t-1)      <- volume: new/exp/contr/churn
--     + MRR_t * (FX_t - FX_(t-1))           <- cambio, nao e decisao comercial
--
-- Sem essa separacao, uma alta do dolar apareceria como "expansao" em clientes
-- que nao compraram nada. Os componentes somam exatamente a variacao do MRR.
-- =====================================================================

-- Moeda de contratacao e atributo estavel da entidade, nao do mes. Verificado
-- que nenhuma entidade tem assinaturas em duas moedas. Isso importa: nos meses
-- em que a entidade nao tem MRR, deduzir a moeda da linha daria NULL e o join
-- de cambio aplicaria a taxa do dolar a um cliente que fatura em real.
CREATE OR REPLACE TABLE dim_entidade_moeda AS
SELECT entidade_id, any_value(moeda) AS moeda
FROM silver_assinaturas_validas
WHERE entidade_id IS NOT NULL
GROUP BY 1;

-- Horizonte com cotacao publicada. A serie de MRR nao pode sair desse intervalo
-- em nenhuma das duas pontas: sem cambio, o MRR em USD viraria NULL e
-- desapareceria silenciosamente da decomposicao, exatamente o tipo de erro que
-- este pipeline existe para evitar. O limite inferior tambem garante que o mes
-- de abertura da serie tenha um mes anterior valido para o lag.
CREATE OR REPLACE TABLE dim_horizonte AS
SELECT min(mes) AS primeiro_mes_com_cambio, max(mes) AS ultimo_mes_com_cambio
FROM silver_fx_mensal;

-- MRR por entidade e mes, em moeda de origem e em BRL.
CREATE OR REPLACE TABLE gold_mrr_entidade_mes AS
WITH vigencia AS (
    SELECT
        d.mes,
        d.fim_mes,
        a.entidade_id,
        a.customer_id,
        a.subscription_id,
        a.plano,
        a.moeda,
        a.ciclo_cobranca,
        a.seats,
        a.mrr_moeda_origem
    FROM seed_dim_mes d
    JOIN silver_assinaturas_validas a
      ON a.start_date <= d.fim_mes
     AND (a.end_date IS NULL OR a.end_date >= d.fim_mes)
    WHERE d.mes BETWEEN (SELECT primeiro_mes_com_cambio FROM dim_horizonte)
                    AND (SELECT ultimo_mes_com_cambio FROM dim_horizonte)
),
por_entidade AS (
    SELECT
        v.mes,
        v.entidade_id,
        any_value(v.plano ORDER BY v.mrr_moeda_origem DESC)          AS plano_principal,
        sum(v.seats)                                                AS seats,
        sum(v.mrr_moeda_origem)                                     AS mrr_origem,
        count(DISTINCT v.subscription_id)                           AS assinaturas_vigentes
    FROM vigencia v
    GROUP BY 1, 2
)
SELECT
    p.mes,
    p.entidade_id,
    em.moeda,
    p.plano_principal,
    p.seats,
    p.assinaturas_vigentes,
    p.mrr_origem,
    CASE WHEN em.moeda = 'BRL' THEN 1.0 ELSE fx.usd_brl_medio END      AS fx_aplicado,
    CASE WHEN em.moeda = 'BRL' THEN p.mrr_origem
         ELSE p.mrr_origem * fx.usd_brl_medio END                     AS mrr_brl
FROM por_entidade p
JOIN dim_entidade_moeda em ON em.entidade_id = p.entidade_id
LEFT JOIN silver_fx_mensal fx ON fx.mes = p.mes;

-- Grade completa entidade x mes, para que ausencia de MRR seja zero explicito
-- e nao linha faltante. Sem isso, churn simplesmente nao aparece.
CREATE OR REPLACE TABLE gold_mrr_grade AS
WITH entidades AS (SELECT DISTINCT entidade_id FROM gold_mrr_entidade_mes),
grade AS (
    SELECT d.mes, d.ordem_mes, e.entidade_id
    FROM seed_dim_mes d CROSS JOIN entidades e
    WHERE d.mes BETWEEN (SELECT primeiro_mes_com_cambio FROM dim_horizonte)
                    AND (SELECT ultimo_mes_com_cambio FROM dim_horizonte)
),
join_mrr AS (
    SELECT
        g.mes,
        g.ordem_mes,
        g.entidade_id,
        coalesce(m.mrr_origem, 0)                                    AS mrr_origem,
        coalesce(m.mrr_brl, 0)                                       AS mrr_brl,
        m.plano_principal,
        em.moeda,
        -- cambio sempre resolvido pela moeda da ENTIDADE, inclusive em mes sem MRR
        CASE WHEN em.moeda = 'BRL' THEN 1.0 ELSE fxm.usd_brl_medio END AS fx_aplicado
    FROM grade g
    JOIN dim_entidade_moeda em        ON em.entidade_id = g.entidade_id
    LEFT JOIN gold_mrr_entidade_mes m ON m.mes = g.mes AND m.entidade_id = g.entidade_id
    LEFT JOIN silver_fx_mensal fxm    ON fxm.mes = g.mes
)
SELECT
    j.*,
    lag(j.mrr_origem) OVER (PARTITION BY j.entidade_id ORDER BY j.ordem_mes) AS mrr_origem_ant,
    lag(j.mrr_brl)    OVER (PARTITION BY j.entidade_id ORDER BY j.ordem_mes) AS mrr_brl_ant,
    lag(j.fx_aplicado) OVER (PARTITION BY j.entidade_id ORDER BY j.ordem_mes) AS fx_ant,
    -- MRR acumulado antes deste mes: distingue cliente novo de reativado
    sum(j.mrr_origem) OVER (PARTITION BY j.entidade_id ORDER BY j.ordem_mes
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS mrr_historico_ant
FROM join_mrr j;

-- Classificacao do movimento de cada entidade em cada mes.
CREATE OR REPLACE TABLE gold_mrr_movimento AS
SELECT
    g.mes,
    g.ordem_mes,
    g.entidade_id,
    g.plano_principal,
    g.moeda,
    g.mrr_origem,
    coalesce(g.mrr_origem_ant, 0)                                    AS mrr_origem_ant,
    g.mrr_brl,
    coalesce(g.mrr_brl_ant, 0)                                       AS mrr_brl_ant,
    g.fx_aplicado,
    coalesce(g.fx_ant, g.fx_aplicado)                                AS fx_ant,
    CASE
        WHEN coalesce(g.mrr_origem_ant, 0) = 0 AND g.mrr_origem > 0
             AND coalesce(g.mrr_historico_ant, 0) = 0                THEN 'novo'
        WHEN coalesce(g.mrr_origem_ant, 0) = 0 AND g.mrr_origem > 0  THEN 'reativacao'
        WHEN coalesce(g.mrr_origem_ant, 0) > 0 AND g.mrr_origem = 0  THEN 'churn'
        WHEN g.mrr_origem > coalesce(g.mrr_origem_ant, 0)            THEN 'expansao'
        WHEN g.mrr_origem < coalesce(g.mrr_origem_ant, 0)            THEN 'contracao'
        WHEN g.mrr_origem > 0                                        THEN 'estavel'
        ELSE 'inativo'
    END                                                              AS movimento,
    -- efeito volume avaliado ao cambio do mes anterior
    (g.mrr_origem - coalesce(g.mrr_origem_ant, 0)) * coalesce(g.fx_ant, g.fx_aplicado)
                                                                     AS delta_volume_brl,
    -- efeito cambial sobre o estoque atual
    g.mrr_origem * (g.fx_aplicado - coalesce(g.fx_ant, g.fx_aplicado))
                                                                     AS delta_cambio_brl
FROM gold_mrr_grade g;

-- Serie executiva de MRR e ARR com a decomposicao que fecha por construcao.
CREATE OR REPLACE TABLE gold_mrr_mensal AS
WITH agg AS (
    SELECT
        m.mes,
        m.ordem_mes,
        sum(m.mrr_brl)                                                           AS mrr_brl,
        sum(m.mrr_brl_ant)                                                       AS mrr_brl_ant,
        count(*) FILTER (WHERE m.mrr_origem > 0)                                 AS clientes_ativos,
        sum(m.delta_volume_brl) FILTER (WHERE m.movimento = 'novo')              AS novo_brl,
        sum(m.delta_volume_brl) FILTER (WHERE m.movimento = 'reativacao')        AS reativacao_brl,
        sum(m.delta_volume_brl) FILTER (WHERE m.movimento = 'expansao')          AS expansao_brl,
        sum(m.delta_volume_brl) FILTER (WHERE m.movimento = 'contracao')         AS contracao_brl,
        sum(m.delta_volume_brl) FILTER (WHERE m.movimento = 'churn')             AS churn_brl,
        sum(m.delta_cambio_brl)                                                  AS efeito_cambio_brl,
        count(*) FILTER (WHERE m.movimento = 'novo')                             AS qtd_novos,
        count(*) FILTER (WHERE m.movimento = 'reativacao')                       AS qtd_reativados,
        count(*) FILTER (WHERE m.movimento = 'churn')                            AS qtd_churn,
        count(*) FILTER (WHERE m.movimento = 'expansao')                         AS qtd_expansao,
        count(*) FILTER (WHERE m.movimento = 'contracao')                        AS qtd_contracao
    FROM gold_mrr_movimento m
    GROUP BY 1, 2
)
SELECT
    a.mes,
    a.ordem_mes,
    a.mrr_brl,
    a.mrr_brl * 12                                                               AS arr_brl,
    a.mrr_brl_ant,
    a.mrr_brl - a.mrr_brl_ant                                                    AS variacao_brl,
    coalesce(a.novo_brl, 0)         AS novo_brl,
    coalesce(a.reativacao_brl, 0)   AS reativacao_brl,
    coalesce(a.expansao_brl, 0)     AS expansao_brl,
    coalesce(a.contracao_brl, 0)    AS contracao_brl,
    coalesce(a.churn_brl, 0)        AS churn_brl,
    coalesce(a.efeito_cambio_brl, 0) AS efeito_cambio_brl,
    -- prova de fechamento: deve ser ~0 em todos os meses
    (a.mrr_brl - a.mrr_brl_ant)
      - (coalesce(a.novo_brl,0) + coalesce(a.reativacao_brl,0) + coalesce(a.expansao_brl,0)
         + coalesce(a.contracao_brl,0) + coalesce(a.churn_brl,0) + coalesce(a.efeito_cambio_brl,0))
                                                                                 AS residuo_decomposicao_brl,
    a.clientes_ativos,
    a.qtd_novos, a.qtd_reativados, a.qtd_churn, a.qtd_expansao, a.qtd_contracao,
    CASE WHEN a.clientes_ativos > 0 THEN a.mrr_brl / a.clientes_ativos END       AS arpa_brl,
    -- churn de receita bruto e liquido sobre a base de abertura
    CASE WHEN a.mrr_brl_ant > 0 THEN -coalesce(a.churn_brl,0) / a.mrr_brl_ant END AS gross_revenue_churn,
    CASE WHEN a.mrr_brl_ant > 0
         THEN -(coalesce(a.churn_brl,0) + coalesce(a.contracao_brl,0)) / a.mrr_brl_ant END
                                                                                 AS gross_churn_com_contracao,
    CASE WHEN a.mrr_brl_ant > 0
         THEN (a.mrr_brl_ant + coalesce(a.expansao_brl,0) + coalesce(a.contracao_brl,0)
               + coalesce(a.churn_brl,0) + coalesce(a.reativacao_brl,0)) / a.mrr_brl_ant END
                                                                                 AS nrr_mensal
FROM agg a
ORDER BY a.ordem_mes;

-- Churn logico de clientes (entidade economica), com base de abertura.
CREATE OR REPLACE TABLE gold_churn_mensal AS
SELECT
    m.mes,
    count(*) FILTER (WHERE m.mrr_origem_ant > 0)                                 AS clientes_abertura,
    count(*) FILTER (WHERE m.movimento = 'churn')                                AS clientes_perdidos,
    CASE WHEN count(*) FILTER (WHERE m.mrr_origem_ant > 0) > 0
         THEN count(*) FILTER (WHERE m.movimento = 'churn')::DOUBLE
              / count(*) FILTER (WHERE m.mrr_origem_ant > 0) END                 AS logo_churn,
    sum(-m.delta_volume_brl) FILTER (WHERE m.movimento = 'churn')                AS mrr_perdido_brl
FROM gold_mrr_movimento m
GROUP BY 1
ORDER BY 1;

-- Tendencia anual do churn: a pergunta 3 e "esta melhorando ou piorando".
CREATE OR REPLACE TABLE gold_churn_tendencia AS
SELECT
    left(c.mes, 4)                                                               AS ano,
    count(*)                                                                     AS meses,
    sum(c.clientes_perdidos)                                                     AS clientes_perdidos,
    sum(c.mrr_perdido_brl)                                                       AS mrr_perdido_brl,
    avg(c.logo_churn)                                                            AS logo_churn_medio_mensal,
    avg(m.gross_revenue_churn)                                                   AS revenue_churn_medio_mensal,
    -- anualizacao composta do churn mensal medio de receita
    1 - power(1 - avg(m.gross_revenue_churn), 12)                                AS revenue_churn_anualizado,
    avg(m.nrr_mensal)                                                            AS nrr_medio_mensal
FROM gold_churn_mensal c
JOIN gold_mrr_mensal m ON m.mes = c.mes
JOIN seed_dim_mes d    ON d.mes = c.mes
WHERE d.dentro_da_janela
GROUP BY 1
ORDER BY 1;

-- NRR de 12 meses: coorte de entidades com MRR na abertura da janela.
CREATE OR REPLACE TABLE gold_nrr_12m AS
WITH par AS (
    SELECT
        (SELECT mes FROM seed_dim_mes WHERE dentro_da_janela ORDER BY ordem_mes DESC LIMIT 1) AS mes_fim
),
base AS (
    SELECT strftime((date_trunc('month', strptime(p.mes_fim, '%Y-%m')) - INTERVAL 12 MONTH), '%Y-%m') AS mes_ini,
           p.mes_fim
    FROM par p
),
coorte AS (
    SELECT g.entidade_id, g.mrr_brl AS mrr_ini, g.mrr_origem AS mrr_ini_origem, g.moeda
    FROM gold_mrr_grade g, base b
    WHERE g.mes = b.mes_ini AND g.mrr_origem > 0
),
fim AS (
    SELECT g.entidade_id, g.mrr_brl AS mrr_fim, g.mrr_origem AS mrr_fim_origem
    FROM gold_mrr_grade g, base b
    WHERE g.mes = b.mes_fim
)
SELECT
    b.mes_ini,
    b.mes_fim,
    count(*)                                                    AS entidades_na_coorte,
    sum(c.mrr_ini)                                              AS mrr_inicial_brl,
    sum(coalesce(f.mrr_fim, 0))                                 AS mrr_final_brl,
    sum(coalesce(f.mrr_fim, 0)) / sum(c.mrr_ini)                AS nrr_brl,
    -- NRR em moeda constante: remove o efeito cambial do indicador
    sum(coalesce(f.mrr_fim_origem, 0)) / sum(c.mrr_ini_origem)  AS nrr_moeda_constante,
    count(*) FILTER (WHERE coalesce(f.mrr_fim, 0) = 0)          AS entidades_perdidas,
    1 - count(*) FILTER (WHERE coalesce(f.mrr_fim, 0) = 0)::DOUBLE / count(*) AS retencao_logica
FROM coorte c
LEFT JOIN fim f USING (entidade_id)
CROSS JOIN base b
GROUP BY 1, 2;

