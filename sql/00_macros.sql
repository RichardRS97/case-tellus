-- =====================================================================
-- 00_macros.sql
-- Funcoes de coercao usadas em toda a camada silver.
-- Ficam isoladas porque parsing de data e de valor monetario e onde este
-- dataset concentra a maior parte dos defeitos: um unico lugar para corrigir.
-- =====================================================================

-- Valor monetario. A origem mistura pt-BR ("2268,00", "1.234,56") com
-- en-US ("349.0"). A presenca de virgula decide o dialeto.
CREATE OR REPLACE MACRO num_flex(s) AS
    TRY_CAST(
        CASE
            WHEN s IS NULL OR trim(s) = '' THEN NULL
            WHEN position(',' IN s) > 0 THEN replace(replace(trim(s), '.', ''), ',', '.')
            ELSE trim(s)
        END AS DOUBLE
    );

-- Data. Tres formatos convivem na mesma coluna do mesmo arquivo:
-- ISO (yyyy-mm-dd), BR com barra (dd/mm/yyyy) e BR com hifen (dd-mm-yyyy).
-- A ordem importa: ISO primeiro para nao ser capturado como dd-mm-yyyy.
-- Confirmado que dd/mm e dd-mm sao dia-primeiro pela existencia de dia > 12
-- em ambos os formatos, o que descarta a leitura mm/dd.
CREATE OR REPLACE MACRO data_flex(s) AS
    TRY_CAST(
        try_strptime(trim(s), ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']) AS DATE
    );

-- Texto de dominio: remove espaco de sobra e uniformiza caixa para join.
CREATE OR REPLACE MACRO chave_dominio(s) AS lower(trim(coalesce(s, '')));

-- CNPJ / tax_id reduzido a digitos, para identificar entidade economica.
CREATE OR REPLACE MACRO so_digitos(s) AS regexp_replace(coalesce(s, ''), '[^0-9]', '', 'g');
