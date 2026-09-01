-- =====================================================================
-- 20_silver_clientes.sql
-- Cadastro de clientes com duas chaves distintas e propositais:
--   customer_id  -> grao contratual (assinatura, fatura)
--   entidade_id  -> grao economico (contagem de clientes, churn, CAC)
-- P08: dois pares de customer_id compartilham CNPJ e sao a mesma empresa.
-- =====================================================================

CREATE OR REPLACE TABLE silver_clientes AS
WITH base AS (
    SELECT
        customer_id,
        trim(legal_name)                          AS razao_social,
        trim(trade_name)                          AS nome_fantasia,
        trim(tax_id)                              AS tax_id,
        so_digitos(tax_id)                        AS tax_id_digitos,
        upper(trim(country))                      AS pais,
        trim(segment)                             AS segmento,
        trim(acquisition_channel)                 AS canal_origem,
        data_flex(signup_date)                    AS signup_date
    FROM bronze_customers
),
canal AS (
    SELECT b.*, coalesce(m.canal_padrao, b.canal_origem) AS canal
    FROM base b
    LEFT JOIN seed_mapa_canal m ON chave_dominio(b.canal_origem) = m.canal_bruto
),
-- entidade economica: menor customer_id entre os que compartilham o CNPJ
entidade AS (
    SELECT tax_id_digitos, min(customer_id) AS entidade_id, count(*) AS ids_no_cnpj
    FROM canal
    GROUP BY 1
)
SELECT
    c.customer_id,
    e.entidade_id,
    e.ids_no_cnpj > 1                             AS cadastro_duplicado,
    c.razao_social,
    c.nome_fantasia,
    c.tax_id,
    c.tax_id_digitos,
    c.pais,
    c.segmento,
    c.canal,
    c.signup_date,
    -- P11: data futura em relacao ao corte e impossivel em export fechado
    c.signup_date > (SELECT data_corte FROM seed_parametros) AS signup_futuro,
    CASE
        WHEN c.signup_date IS NULL THEN 'signup_date ilegivel'
        WHEN c.signup_date > (SELECT data_corte FROM seed_parametros) THEN 'signup_date posterior a data de corte'
    END                                           AS motivo_quarentena
FROM canal c
JOIN entidade e USING (tax_id_digitos);

-- Data de aquisicao da entidade economica = primeiro signup valido entre os
-- cadastros que a compoem. Usado por coorte de CAC e por churn logico.
CREATE OR REPLACE TABLE silver_entidades AS
SELECT
    entidade_id,
    any_value(nome_fantasia ORDER BY customer_id)  AS nome_fantasia,
    any_value(pais          ORDER BY customer_id)  AS pais,
    any_value(segmento      ORDER BY customer_id)  AS segmento,
    any_value(canal         ORDER BY customer_id)  AS canal,
    min(signup_date) FILTER (WHERE NOT coalesce(signup_futuro, TRUE)) AS signup_date,
    count(*)                                       AS qtd_customer_id,
    bool_or(cadastro_duplicado)                    AS cadastro_duplicado
FROM silver_clientes
GROUP BY 1;

CREATE OR REPLACE TABLE quarentena_clientes AS
SELECT customer_id, motivo_quarentena, signup_date
FROM silver_clientes
WHERE motivo_quarentena IS NOT NULL;
