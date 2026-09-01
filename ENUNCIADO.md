# Case técnico — Data Finance

## Unit economics da Tellus

---

## O contexto

A **Tellus Tecnologia S.A.** é um SaaS B2B de roteirização e gestão de entregas. Cobra por assento (motorista/veículo ativo), em três planos — Starter, Growth e Enterprise — com contratos mensais ou anuais. Vende no Brasil (em BRL) e no México e Estados Unidos (em USD).

A empresa cresceu rápido nos últimos dois anos e hoje o board pede números que ninguém consegue produzir de forma confiável. Cada área tem sua própria planilha: Vendas olha MRR, Contabilidade olha receita reconhecida, Infra olha custo de cloud, e os três números nunca conversam. Ninguém sabe dizer com segurança qual cliente dá lucro.

Você foi contratado para resolver isso. Este case é o primeiro entregável.

**Moeda de reporte: BRL.** Período de análise: **janeiro/2024 a junho/2026**. A data de corte dos dados é **15/07/2026** — trate hoje como sendo essa data.

---

## As fontes

Estão na pasta `dados_case_tellus/`. São exports reais de sistemas diferentes, com todos os defeitos que isso implica.

### 1. `tellus_financeiro.db` — SQLite

Banco do time financeiro, três tabelas:

- **`customers`** — cadastro de clientes: `customer_id`, `legal_name`, `trade_name`, `tax_id`, `country`, `segment`, `acquisition_channel`, `signup_date`
- **`payments`** — movimentação de caixa: `payment_id`, `numero_fatura`, `paid_at`, `amount`, `currency`, `method`
- **`sales_marketing_spend`** — investimento mensal em aquisição, por canal: `month`, `channel`, `spend_brl`

### 2. `faturas_export.csv` — sistema de cobrança

Export automático do "Cobranças v4.2". Uma linha por documento fiscal emitido. Contém faturas e notas de crédito. As colunas de competência (`competencia_inicio`, `competencia_fim`) indicam o período de serviço que o documento cobre — que não é necessariamente o mês da emissão.

### 3. `assinaturas.jsonl` — plataforma do produto

Um JSON por linha, uma linha por assinatura. Mudanças de plano ou de quantidade de assentos geram uma nova assinatura e encerram a anterior. `unit_price` é o **preço mensal por assento**, na mesma base para os dois ciclos de cobrança — contratos anuais não têm o preço anualizado nesse campo.

### 4. `infra_costs.csv` + `workspace_map.csv` — cloud

Custo mensal de infraestrutura em **USD**, por workspace e por serviço (`compute`, `storage`, `egress`, `ai_tokens`). O `workspace_map.csv` liga workspace a cliente.

### 5. Câmbio — API do Banco Central (extração obrigatória)

Você deve **buscar as cotações via API**, não hardcodar. Use a API de dados abertos do SGS, série 1 (dólar comercial, venda):

```
https://api.bcb.gov.br/dados/serie/
```

Descobrir os parâmetros de chamada e o período que você precisa buscar faz parte do exercício.

---

## O que queremos saber

Sete perguntas. As seis primeiras são sobre os números, e não são independentes — respondê-las bem exige um modelo de dados comum, não seis análises soltas. A sétima é sobre o que acontece depois que você entrega.

**1. Receita reconhecida × receita em caixa.** Qual foi a receita reconhecida (competência) por mês, em BRL, no período? E quanto entrou de caixa em cada mês? Por que os dois números diferem, e qual o saldo de receita diferida no fechamento de junho/2026?

**2. MRR e ARR.** Qual o MRR no fechamento de cada mês? Decomponha a variação mês a mês em suas causas (novo, expansão, contração, churn e o que mais você julgar necessário). Qual a Net Revenue Retention?

**3. Churn.** Quanto a Tellus perde por churn, e a situação está melhorando ou piorando?

**4. Margem bruta.** Qual a margem bruta por mês, por plano e por cliente? A trajetória da margem está estável? Se não, o que a explica?

**5. CAC, payback e LTV.** Quanto custa adquirir um cliente, por coorte e por canal de aquisição? Em quanto tempo esse custo se paga? Qual o LTV, e qual a razão LTV/CAC?

**6. Qualidade dos dados.** O que você encontrou de errado, ambíguo ou não confiável nas fontes? Para cada item: qual o impacto nos números e o que você pediria para corrigir na origem.

**7. Perenidade e linguagem comum.** O que você construiu aqui precisa continuar existindo e correto depois que você sair de férias, e Vendas, Contabilidade e Infra precisam parar de operar cada um com a sua definição de MRR, receita e churn. Como você faria para que as definições que você escolheu neste case virem *as* definições da empresa — e continuem valendo daqui a um ano, com gente nova, fontes novas e alguém pedindo um número às 18h de um dia de fechamento?

Queremos mecanismo concreto, não intenção. "Documentar bem" e "alinhar com as áreas" não são respostas; *como* se documenta, *quem* aprova uma mudança de definição, *o que* quebra o pipeline quando alguém contraria a regra — são. Responda em até 1 página, no README ou em documento à parte. Não precisa implementar; se implementou parte disso no case, aponte onde.

> **Sobre as definições:** algumas perguntas usam termos que admitem mais de uma leitura. Não vamos esclarecer qual queremos. Escolha, justifique e documente a premissa — a escolha e a justificativa fazem parte da avaliação, tanto quanto o número.

---

## Entregáveis

**1. Repositório Git** com o pipeline completo. Requisito firme: **um comando roda tudo do zero**, das fontes cruas às tabelas finais, de forma reproduzível e idempotente. Rodar duas vezes seguidas não pode alterar o resultado.

**2. Modelagem em camadas explícitas** (bronze / silver / gold, ou nomenclatura equivalente que você defenda). As tabelas finais que alimentam a visualização devem estar na camada de consumo.

**3. Visualização** — ferramenta livre (Streamlit, Metabase, Superset, Looker Studio, Evidence, um notebook bem feito, o que você preferir). Precisa cobrir no mínimo:

- evolução de MRR com a decomposição da variação
- margem bruta ao longo do tempo
- uma visão por cliente que permita identificar quem dá e quem não dá lucro

**4. `README.md`** com: como rodar, decisões de modelagem, **premissas assumidas** (essa seção importa muito), limitações conhecidas e o que você faria com mais tempo.

**5. Resumo executivo — 1 página.** Escrito para o Head of Finance, não para o time de dados. As três coisas que ele precisa saber e o que fazer a respeito.

---

## Regras

- **Core em Python e SQL.** O motor do pipeline e as transformações devem estar nessas duas linguagens. Orquestração, engine (DuckDB, Postgres, Spark, pandas, Polars…), estrutura de projeto e ferramenta de visualização são sua escolha — e você vai ser perguntado sobre o porquê.
- **Assistentes de IA são permitidos e esperados.** Mas você vai defender o código linha a linha na conversa. Não entregue o que você não sabe explicar.
- **Esforço esperado: 4 a 6 horas, com entrega no mesmo dia** em que você recebe o material.
- **Não é esperado que você termine tudo.** Preferimos três perguntas respondidas com rigor a sete respondidas por cima. Se cortar escopo, diga no README o que cortou e por quê. A pergunta 7 é a exceção: ela custa pouco tempo e queremos a resposta de todo mundo.
- **Dúvidas são bem-vindas** — mande por e-mail. Perguntar não desconta nota; perguntar bem conta a favor. Mas não vamos responder o que a pergunta 6 pede que você descubra.

---

## Como vamos avaliar

| Dimensão | Peso | O que olhamos |
|---|---|---|
| **Corretude dos números** | 30% | Os valores fecham? As reconciliações batem? Erros de competência, câmbio, sinal ou duplicidade? |
| **Engenharia de dados** | 25% | Modelagem, idempotência, reprodutibilidade, tratamento de casos de borda, testes, legibilidade |
| **Julgamento de negócio** | 25% | As premissas fazem sentido para uma empresa de verdade? Estão documentadas? As ambiguidades foram percebidas? A resposta da pergunta 7 propõe mecanismo ou só boa vontade? |
| **Comunicação e visualização** | 20% | Um executivo entende sozinho? A visualização responde à pergunta ou só mostra dados? |

Peso deliberadamente alto em corretude: em finanças, um dashboard bonito com o número errado é pior do que nenhum dashboard.

---

## Conversa de defesa

Depois da entrega, **45 minutos** com o time. Vamos pedir para você:

- justificar as premissas que escolheu, especialmente onde a definição era ambígua
- percorrer um número específico da fonte crua até o dashboard
- responder a uma mudança de requisito ao vivo, com o código aberto

Não é pegadinha. É a rotina da vaga.

---

**Boa sorte.** Qualquer problema com os arquivos ou com o enunciado, escreva imediatamente — não perca tempo do case travado em algo que a gente resolve em cinco minutos.
