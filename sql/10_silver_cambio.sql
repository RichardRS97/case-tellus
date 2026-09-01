-- =====================================================================
-- 10_silver_cambio.sql
-- Cambio PTAX venda em dois graos: diario com forward-fill (para caixa) e
-- medio mensal (para fluxos de competencia).
-- =====================================================================

CREATE OR REPLACE TABLE silver_fx_diario AS
SELECT
    data::DATE                        AS data,
    taxa::DOUBLE                      AS usd_brl,
    preenchida::BOOLEAN               AS taxa_por_forward_fill
FROM bronze_fx_diario;

-- Media aritmetica das cotacoes efetivamente publicadas no mes (dias uteis).
-- Deliberadamente exclui dias de forward-fill: incluir fim de semana daria
-- peso extra a sexta-feira e enviesaria a media do mes.
CREATE OR REPLACE TABLE silver_fx_mensal AS
SELECT
    strftime(data, '%Y-%m')           AS mes,
    avg(usd_brl)                      AS usd_brl_medio,
    count(*)                          AS dias_uteis_publicados,
    min(usd_brl)                      AS usd_brl_min,
    max(usd_brl)                      AS usd_brl_max
FROM silver_fx_diario
WHERE NOT taxa_por_forward_fill
GROUP BY 1;
