"""Configuracao central e contrato de premissas do pipeline Tellus.

Toda premissa de negocio que admite mais de uma leitura esta declarada aqui,
com identificador estavel (PREMISSA_XX). O relatorio e o README leem esta
estrutura, de modo que nao existe premissa documentada em prosa que nao esteja
tambem vigente no codigo. Mudar a regra exige mudar este arquivo, o que deixa
rastro em code review.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

# ----------------------------------------------------------------- caminhos
ROOT = Path(__file__).resolve().parent.parent
# Fontes originais vivem DENTRO do repositorio, em dados_originais/. Isso e
# deliberado: o requisito do enunciado e "um comando roda tudo do zero" a
# partir de um clone do repositorio, o que exige que a fonte crua nao dependa
# de nenhum caminho fora dele.
SOURCE_DIR = ROOT / "dados_originais"
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"

DUCKDB_PATH = DATA_DIR / "tellus_warehouse.duckdb"
FX_CACHE = DATA_DIR / "fx_ptax_cache.json"

SRC_FATURAS = SOURCE_DIR / "faturas_export.csv"
SRC_ASSINATURAS = SOURCE_DIR / "assinaturas.jsonl"
SRC_INFRA = SOURCE_DIR / "infra_costs.csv"
SRC_WSMAP = SOURCE_DIR / "workspace_map.csv"
SRC_SQLITE = SOURCE_DIR / "tellus_financeiro.db"

# ----------------------------------------------------------------- periodo
DATA_CORTE = date(2026, 7, 15)      # "hoje" segundo o enunciado
PERIODO_INI = date(2024, 1, 1)      # inicio da janela de analise
PERIODO_FIM = date(2026, 6, 30)     # fim da janela de analise
MOEDA_REPORTE = "BRL"

# API de dados abertos do Banco Central, SGS serie 1 = dolar comercial venda.
BCB_SERIE_DOLAR_VENDA = 1
BCB_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
# Buffer para tras: a assinatura mais antiga comeca em jan/2022 e ha faturas de
# 2023 cuja competencia invade 2024. O mes anterior ao primeiro dado e necessario
# para que o lag da decomposicao de MRR e o forward-fill tenham dia util previo.
FX_INI = date(2021, 12, 1)
FX_FIM = DATA_CORTE

# ----------------------------------------------------------------- premissas
PREMISSAS: dict[str, dict[str, str]] = {
    "P01": {
        "tema": "Receita reconhecida",
        "regra": "Rateio pro-rata diario do valor liquido do documento ao longo de "
                 "[competencia_inicio, competencia_fim], nunca pela data de emissao.",
        "porque": "Competencia e o periodo de servico prestado. Contratos anuais faturados "
                  "de uma vez (53 documentos, ate 13 meses de cobertura) reconhecidos na "
                  "emissao criariam picos de receita inexistentes e receita diferida errada.",
        "alternativa": "Reconhecer por mes-calendario inteiro. Rejeitada: 41 documentos tem "
                       "competencia comecando no meio do mes, o que geraria receita em mes "
                       "sem servico prestado.",
    },
    "P02": {
        "tema": "Documentos elegiveis a receita",
        "regra": "Exclui status CANCELADA. Inclui ABERTA e VENCIDA (fato gerador ocorreu). "
                 "NOTA_CREDITO entra com sinal invertido (redutor de receita).",
        "porque": "Receita reconhecida e independente de recebimento; cancelamento anula o "
                  "fato gerador. As 35 notas de credito estao gravadas com valor POSITIVO na "
                  "origem, somar sem inverter o sinal infla a receita duas vezes o valor.",
        "alternativa": "Excluir VENCIDA. Rejeitada: confundiria risco de credito com receita, "
                       "inadimplencia e tratada como perda, nao como ausencia de receita.",
    },
    "P03": {
        "tema": "Cambio de fluxos (receita e custo)",
        "regra": "PTAX venda (SGS serie 1) media do mes de competencia, aplicada ao mes em "
                 "que a receita e reconhecida ou o custo e incorrido.",
        "porque": "IAS 21 / CPC 02 admitem taxa media do periodo para transacoes recorrentes. "
                  "Da estabilidade ao serie temporal sem introduzir vies de data unica.",
        "alternativa": "Taxa do dia da emissao. Rejeitada para receita rateada: um contrato "
                       "anual ficaria travado no cambio de um unico dia por 13 meses.",
    },
    "P04": {
        "tema": "Cambio de caixa",
        "regra": "PTAX venda do dia do pagamento, com forward-fill do ultimo dia util para "
                 "pagamentos em fim de semana ou feriado.",
        "porque": "Caixa e evento pontual e datado; a taxa relevante e a da liquidacao.",
        "alternativa": "Taxa media do mes. Rejeitada: destruiria a reconciliacao com extrato.",
    },
    "P05": {
        "tema": "Deduplicacao de faturas",
        "regra": "numero_fatura e a chave de negocio. Em duplicidade, mantem 1 linha por "
                 "numero_fatura escolhida deterministicamente (data em formato ISO primeiro, "
                 "depois ordem alfabetica do restante).",
        "porque": "47 documentos aparecem 2x, com cliente, valor, moeda e tipo identicos e "
                  "apenas o formato da data diferente: e reexportacao do mesmo documento, nao "
                  "cobranca em dobro. Determinismo na escolha garante idempotencia.",
        "alternativa": "Somar as duas linhas. Rejeitada: inflaria a receita em BRL 1,26 mi.",
    },
    "P06": {
        "tema": "MRR",
        "regra": "MRR do mes = soma, sobre assinaturas vigentes no ultimo dia do mes, de "
                 "seats * unit_price convertido a BRL. unit_price ja e mensal por assento nos "
                 "dois ciclos de cobranca.",
        "porque": "O enunciado e explicito: contratos anuais NAO tem preco anualizado no campo. "
                  "Multiplicar anual por 12 inflaria o MRR de 50 assinaturas.",
        "alternativa": "MRR como receita reconhecida do mes. Rejeitada: mistura receita "
                       "contratada recorrente com efeito de pro-rata e nota de credito.",
    },
    "P07": {
        "tema": "Duplicidade de assinaturas e sobreposicao",
        "regra": "6 subscription_id aparecem 2x com as duas linhas byte-a-byte identicas: "
                 "dedup pela chave. Verificado apos dedup que NAO resta sobreposicao de "
                 "vigencia em nenhum cliente, portanto nenhuma regra de truncamento e aplicada.",
        "porque": "A sobreposicao aparente de 5 pares era artefato da propria duplicidade, o "
                  "registro sobrepondo era ele mesmo. Criar regra de truncamento aqui seria "
                  "corrigir um problema que nao existe e mascararia sobreposicao futura real.",
        "alternativa": "Truncar vigencia da anterior em (start da seguinte - 1 dia). Nao "
                       "aplicada, mas o teste que detectaria a necessidade fica no pipeline e "
                       "falha se sobreposicao real aparecer em carga futura.",
    },
    "P08": {
        "tema": "Identidade do cliente",
        "regra": "Entidade economica = tax_id normalizado. Dois pares de customer_id "
                 "compartilham CNPJ (Girassol Express, Duna Transportes) e sao consolidados "
                 "para contagem de clientes, churn e CAC.",
        "porque": "Cadastro duplicado contaria a mesma empresa como dois clientes, inflando "
                  "aquisicao e distorcendo churn logico e CAC.",
        "alternativa": "Tratar customer_id como entidade. Mantido apenas no grao de assinatura "
                       "e faturamento, onde o contrato e por customer_id.",
    },
    "P09": {
        "tema": "COGS atribuivel",
        "regra": "COGS de cliente = custo dos workspaces mapeados a ele. Os 27 workspaces sem "
                 "mapeamento (50,6% do custo, USD 635 mil) NAO sao rateados: ficam em COGS "
                 "nao atribuivel e a margem e reportada em duas camadas (direta e consolidada).",
        "porque": "Ratear por receita converteria uma falha de governanca de tags em numero "
                  "inventado, e margem por cliente e usada para decisao comercial. O mix de "
                  "servico identico e o custo medio 4x maior indicam plataforma compartilhada "
                  "ou bloco de contas sem dono, nao ruido.",
        "alternativa": "Ratear pro-rata da receita. Disponivel no modelo como cenario "
                       "sensibilizado, nunca como numero principal.",
    },
    "P10": {
        "tema": "Canal de aquisicao",
        "regra": "PLG (em customers) e Product-Led (em spend) sao o mesmo canal. Brand existe "
                 "so em spend e nao tem cliente atribuivel: entra apenas no CAC blended.",
        "porque": "Sem o mapeamento, o CAC de PLG fica infinito e o de Product-Led fica zero. "
                  "Brand e investimento de topo de funil, atribuir a um canal seria arbitrario.",
        "alternativa": "Ratear Brand pelos demais canais. Rejeitada como numero principal, "
                       "reportada como sensibilidade.",
    },
    "P11": {
        "tema": "Registros impossiveis",
        "regra": "signup_date, data_emissao ou paid_at posteriores a 15/07/2026 sao quarentenados. "
                 "As 5 assinaturas com end_date < start_date tem a vigencia reparada pela regra "
                 "de sucessao (end_date = start_date da assinatura seguinte do mesmo cliente "
                 "menos 1 dia); se nao houver sucessora, vao para quarentena.",
        "porque": "Data futura em export fechado nao pode existir. Para a vigencia invertida, o "
                  "proprio enunciado define que mudanca de plano encerra a assinatura anterior, "
                  "logo o fim correto e derivavel do inicio da sucessora, sem inventar valor. "
                  "Todas as 5 tem status upgraded/downgraded/canceled, coerente com sucessao.",
        "alternativa": "Descartar as 5. Rejeitada: 3 estao dentro da janela de analise e o "
                       "descarte abriria buraco de MRR em cliente que seguiu ativo.",
    },
    "P13": {
        "tema": "Assinatura com zero assentos",
        "regra": "3 assinaturas tem seats = 0 (duas ainda ativas). Sao quarentenadas do calculo "
                 "de MRR, com o impacto medido e reportado, nunca imputadas.",
        "porque": "O modelo de cobranca e por assento: zero assento em plano Enterprise ativo e "
                  "impossivel do ponto de vista de negocio. Imputar pela mediana do plano "
                  "produziria MRR que nenhum contrato sustenta.",
        "alternativa": "Imputar mediana de assentos do plano. Rejeitada: seria receita inventada "
                       "em cima de um defeito de cadastro que precisa ser corrigido na origem.",
    },
    "P14": {
        "tema": "Anomalia imaterial declarada",
        "regra": "4 assinaturas com billing_period nulo sao mantidas, marcadas como 'desconhecido'.",
        "porque": "unit_price e mensal nos dois ciclos de cobranca, portanto o ciclo nao entra no "
                  "calculo de MRR nem de receita reconhecida. O impacto no numero e exatamente "
                  "zero. Declarar isso evita que a anomalia seja usada para desqualificar o "
                  "resultado e mostra a diferenca entre defeito de dado e defeito de metrica.",
        "alternativa": "Quarentenar por precaucao. Rejeitada: perderia MRR real por um campo "
                       "que nao participa de nenhuma formula.",
    },
    "P12": {
        "tema": "LTV",
        "regra": "LTV = ARPA mensal * margem bruta % / gross revenue churn mensal, com churn "
                 "medido em receita, nao em contagem de clientes.",
        "porque": "LTV sobre receita bruta ignora que servir o cliente custa dinheiro; sobre "
                  "churn logico ignora que os clientes que saem nao tem o ticket medio.",
        "alternativa": "LTV = ARPA / churn logico. Reportada em paralelo para evidenciar a "
                       "diferenca de magnitude.",
    },
    "P15": {
        "tema": "Workspace com mais de um cliente declarado",
        "regra": "3 workspaces (ws-0043, ws-0053, ws-0056) aparecem no mapa apontando para dois "
                 "customer_id diferentes, com CNPJ e razao social distintos, somando USD 51 mil. "
                 "O custo desses workspaces vai para COGS nao atribuivel, com motivo proprio.",
        "porque": "Nao e duplicidade e sim conflito de atribuicao. Manter as duas linhas causaria "
                  "fan-out no join e duplicaria o custo; escolher um dono por ordem alfabetica "
                  "atribuiria despesa de uma empresa a outra em analise de rentabilidade.",
        "alternativa": "Dividir o custo 50/50 entre os dois candidatos. Rejeitada: nenhuma "
                       "evidencia nos dados sustenta a proporcao e o erro ficaria invisivel.",
    },
}

# Normalizacao de dominios: mapa unico, consumido pelo SQL via tabela seed.
MAPA_PLANO = {
    "starter": "Starter", "growth": "Growth", "enterprise": "Enterprise", "ent": "Enterprise",
}
MAPA_CANAL = {
    "plg": "Product-Led", "product-led": "Product-Led", "inbound": "Inbound",
    "outbound": "Outbound", "partner": "Partner", "brand": "Brand",
}
CANAIS_SEM_ATRIBUICAO = ("Brand",)

# Precos de tabela observados, usados para validacao de sanidade, nao para imputacao.
PRECO_TABELA = {
    ("Starter", "BRL"): 89.0, ("Growth", "BRL"): 189.0, ("Enterprise", "BRL"): 349.0,
    ("Starter", "USD"): 19.0, ("Growth", "USD"): 39.0, ("Enterprise", "USD"): 69.0,
}
