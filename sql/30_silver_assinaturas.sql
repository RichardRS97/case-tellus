-- =====================================================================
-- 30_silver_assinaturas.sql
-- Normalizacao de plano, coercao de tipos, dedup e reparo de vigencia.
-- Concentra P06, P07, P11 e P13.
-- =====================================================================

CREATE OR REPLACE TABLE silver_assinaturas AS
WITH bruto AS (
    SELECT
        subscription_id,
        customer_id,
        plan                                        AS plano_bruto,
        seats                                       AS seats_bruto,
        unit_price                                  AS unit_price_bruto,
        upper(trim(currency))                       AS moeda,
        lower(trim(coalesce(billing_period, '')))   AS ciclo_bruto,
        data_flex(start_date)                       AS start_date,
        data_flex(end_date)                         AS end_date,
        data_flex(canceled_at)                      AS canceled_at,
        lower(trim(status))                         AS status,
        _hash_linha
    FROM bronze_assinaturas
),
-- P07: 6 subscription_id vem duplicados com as duas linhas identicas.
-- row_number sobre a chave de negocio, ordenado por hash, e deterministico:
-- roda duas vezes e escolhe sempre a mesma linha (exigencia de idempotencia).
dedup AS (
    SELECT *, row_number() OVER (PARTITION BY subscription_id ORDER BY _hash_linha) AS rn,
           count(*)       OVER (PARTITION BY subscription_id)                       AS copias
    FROM bruto
),
tipado AS (
    SELECT
        d.subscription_id,
        d.customer_id,
        -- P06: plano vem com 13 grafias distintas para 3 planos reais
        coalesce(m.plano_padrao, 'NAO_MAPEADO')     AS plano,
        d.plano_bruto,
        -- seats vem como int em 203 linhas e como texto em 15
        TRY_CAST(num_flex(d.seats_bruto) AS INTEGER) AS seats,
        num_flex(d.unit_price_bruto)                AS unit_price,
        d.moeda,
        CASE WHEN d.ciclo_bruto = '' THEN 'desconhecido' ELSE d.ciclo_bruto END AS ciclo_cobranca,
        d.start_date,
        d.end_date,
        d.canceled_at,
        d.status,
        d.copias > 1                                AS veio_duplicada,
        d._hash_linha
    FROM dedup d
    LEFT JOIN seed_mapa_plano m ON chave_dominio(d.plano_bruto) = m.plano_bruto
    WHERE d.rn = 1
),
-- P11: 5 assinaturas tem end_date anterior ao start_date. Todas com status de
-- sucessao (upgraded/downgraded/canceled), o que permite derivar o fim correto
-- do inicio da assinatura seguinte do mesmo cliente, sem inventar data.
sucessao AS (
    SELECT
        t.*,
        lead(t.start_date) OVER (PARTITION BY t.customer_id ORDER BY t.start_date, t.subscription_id)
            AS proximo_inicio
    FROM tipado t
),
reparo AS (
    SELECT
        s.* EXCLUDE (end_date),
        CASE
            WHEN s.end_date IS NOT NULL AND s.end_date < s.start_date AND s.proximo_inicio IS NOT NULL
                THEN s.proximo_inicio - INTERVAL 1 DAY
            ELSE s.end_date
        END::DATE                                   AS end_date,
        s.end_date                                  AS end_date_origem,
        s.end_date IS NOT NULL AND s.end_date < s.start_date AS vigencia_invertida_na_origem
    FROM sucessao s
)
SELECT
    r.subscription_id,
    r.customer_id,
    c.entidade_id,
    r.plano,
    r.plano_bruto,
    r.seats,
    r.unit_price,
    r.moeda,
    r.ciclo_cobranca,
    r.start_date,
    r.end_date,
    r.end_date_origem,
    r.canceled_at,
    r.status,
    r.veio_duplicada,
    r.vigencia_invertida_na_origem,
    -- MRR contratado em moeda de origem. unit_price ja e mensal por assento
    -- nos dois ciclos (enunciado explicito): nao ha anualizacao aqui.
    r.seats * r.unit_price                          AS mrr_moeda_origem,
    CASE
        WHEN r.start_date IS NULL                              THEN 'start_date ilegivel'
        WHEN r.plano = 'NAO_MAPEADO'                           THEN 'plano fora do dominio conhecido'
        WHEN r.seats IS NULL                                   THEN 'seats ilegivel'
        WHEN r.seats <= 0                                      THEN 'seats zero ou negativo'
        WHEN r.unit_price IS NULL OR r.unit_price <= 0          THEN 'unit_price ausente ou nao positivo'
        WHEN r.end_date IS NOT NULL AND r.end_date < r.start_date
                                                               THEN 'vigencia invertida sem sucessora para reparo'
    END                                             AS motivo_quarentena
FROM reparo r
LEFT JOIN silver_clientes c ON c.customer_id = r.customer_id;

CREATE OR REPLACE TABLE quarentena_assinaturas AS
SELECT subscription_id, customer_id, plano, seats, unit_price, start_date, end_date,
       status, motivo_quarentena, seats * unit_price AS mrr_perdido_moeda_origem, moeda
FROM silver_assinaturas
WHERE motivo_quarentena IS NOT NULL;

-- Assinaturas aptas a compor MRR.
CREATE OR REPLACE TABLE silver_assinaturas_validas AS
SELECT * FROM silver_assinaturas WHERE motivo_quarentena IS NULL;

-- Teste vivo de P07: se uma carga futura trouxer sobreposicao real de vigencia
-- no mesmo cliente, esta tabela deixa de ser vazia e o pipeline falha em checks.
CREATE OR REPLACE TABLE alerta_sobreposicao_vigencia AS
SELECT
    a.customer_id,
    a.subscription_id                              AS assinatura_anterior,
    a.start_date                                   AS inicio_anterior,
    a.end_date                                     AS fim_anterior,
    b.subscription_id                              AS assinatura_seguinte,
    b.start_date                                   AS inicio_seguinte
FROM silver_assinaturas_validas a
JOIN silver_assinaturas_validas b
  ON a.customer_id = b.customer_id
 AND a.subscription_id <> b.subscription_id
 AND b.start_date > a.start_date
 AND a.end_date IS NOT NULL
 AND b.start_date < a.end_date;
