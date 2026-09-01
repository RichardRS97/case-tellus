# Tellus Tecnologia | Unit Economics

Resolução do case técnico de Data Finance. Pipeline em camadas que sai dos exports crus
das cinco fontes e chega em indicadores auditáveis de receita, MRR, churn, margem bruta e
unit economics, com moeda de reporte em BRL.

**Tudo roda localmente.** Nenhum dado sai da máquina, nenhum serviço de nuvem é usado, nenhuma
tabela é criada em plataforma externa. A única chamada de rede é a API pública de dados abertos
do Banco Central, exigida pelo enunciado, e o resultado dela fica em cache local.

---

## Como rodar

Requisito: Python 3.11 ou superior.

```bash
pip install -r requirements.txt
python run.py
```

Um comando reconstrói tudo do zero: ingestão das fontes, câmbio, transformações, verificações e
relatório. Ao terminar, abra `out/relatorio_tellus.html` com duplo clique.

| Comando | O que faz |
|---|---|
| `python run.py` | Pipeline completo, verificações e relatório |
| `python run.py --idempotencia` | Executa duas vezes e compara as tabelas de consumo |
| `python run.py --forcar-fx` | Refaz a extração de câmbio na API do BCB, ignorando o cache |
| `python run.py --sem-relatorio` | Somente pipeline e verificações |
| `python run.py -v` | Log em nível debug |

O processo devolve código de saída `0` quando aprovado, `1` quando alguma verificação bloqueante
falha e `2` quando a idempotência é violada. Serve para uso em agendador sem supervisão.

### Onde ficam as fontes

As fontes originais vivem dentro do próprio repositório, em `dados_originais/`. Isso é deliberado:
o requisito de "um comando roda tudo do zero" precisa valer a partir de um `git clone` limpo, em
qualquer máquina, sem depender de nenhum caminho fora do repositório.

---

## Estrutura

```
case_tellus_solucao/
├── run.py                      ponto de entrada único
├── requirements.txt
├── README.md
├── RESUMO_EXECUTIVO.md         uma página para o Head de Finance
├── DIARIO_TECNICO.md           jornada de diagnóstico e decisões, para estudo
├── dados_originais/            fontes cruas, exatamente como recebidas
├── src/
│   ├── config.py               parâmetros e as 15 premissas de negócio
│   ├── fx.py                   extração PTAX na API do BCB, com cache e validação
│   ├── bronze.py               ingestão fiel das fontes, com linhagem por linha
│   ├── pipeline.py             orquestração e seeds
│   ├── checks.py               26 verificações de reconciliação
│   ├── viz.py                  gráficos SVG gerados em Python
│   └── report.py               relatório HTML autocontido
├── sql/                        transformações, executadas na ordem numérica
│   ├── 00_macros.sql           coerção de data e de valor monetário
│   ├── 10_silver_cambio.sql
│   ├── 20_silver_clientes.sql
│   ├── 30_silver_assinaturas.sql
│   ├── 40_silver_faturas.sql   receita reconhecida e receita diferida
│   ├── 50_silver_caixa_infra.sql
│   ├── 60_gold_receita_caixa.sql
│   ├── 70_gold_mrr.sql         MRR, decomposição, NRR, churn
│   ├── 80_gold_margem.sql
│   ├── 90_gold_unit_economics.sql
│   └── 95_naive.sql            versão sem tratamento e bridge de erro
├── analise_exploratoria/       auditoria inicial das fontes (evidência do diagnóstico)
├── data/                       warehouse DuckDB e cache de câmbio (gerados)
└── out/                        relatório e logs (gerados)
```

---

## Decisões de modelagem

### Por que DuckDB

O volume total é de aproximadamente 13 mil linhas. Postgres ou Spark seriam infraestrutura sem
problema correspondente. DuckDB dá SQL analítico completo (`QUALIFY`, `FILTER`, funções de janela,
`generate_series`) em um arquivo local, sem servidor, o que mantém o requisito de um comando rodar
tudo do zero em qualquer máquina. As transformações estão em SQL versionado, não em strings dentro
do Python, para que sejam revisáveis e testáveis isoladamente.

A leitura do SQLite de origem usa o módulo `sqlite3` da biblioteca padrão em vez da extensão do
DuckDB, para que o pipeline não precise baixar extensão em tempo de execução e continue funcionando
offline depois do primeiro cache de câmbio.

### Camadas

**Bronze** recebe tudo como texto, exatamente como veio, sem nenhuma correção. Cada linha carrega
arquivo de origem, encoding detectado, número da linha física e hash do conteúdo. Isso é o que
permite pegar qualquer número do relatório e voltar até a linha exata do arquivo cru.

**Silver** conforma: parsing de data e valor, normalização de domínio, deduplicação e quarentena.
Registro com defeito impeditivo não é apagado nem corrigido por adivinhação, vai para uma tabela
`quarentena_*` com o motivo, e o volume aparece no relatório.

**Gold** entrega os indicadores. É a única camada que as áreas consomem.

### Duas decisões que mudam o resultado

**Receita é reconhecida por rateio diário sobre a competência, nunca pela emissão.** Cinquenta e
três documentos cobrem mais de dois meses, com até treze meses de competência. Reconhecer na emissão
criaria picos de receita inexistentes e um saldo de receita diferida errado.

**O custo de cloud sem dono não é rateado.** Metade do COGS não tem cliente identificável. Ratear
por receita produziria margem por cliente com aparência de precisão e sem lastro, e essa margem
seria usada para decidir preço. O relatório mostra margem direta como piso e margem consolidada como
teto, e diz que a verdade está entre as duas.

### Efeito cambial isolado na decomposição de MRR

A decomposição separa efeito de volume de efeito de câmbio por uma identidade algébrica exata:

```
MRR_t · FX_t − MRR_(t−1) · FX_(t−1)
  = (MRR_t − MRR_(t−1)) · FX_(t−1)     efeito de volume: novo, expansão, contração, churn
  + MRR_t · (FX_t − FX_(t−1))          efeito cambial
```

Sem essa separação, uma alta do dólar apareceria como expansão de receita em clientes que não
compraram nenhum assento novo. Os componentes somam exatamente a variação do MRR, e o resíduo é
verificado a cada execução.

---

## Premissas assumidas

As quinze premissas vivem em `src/config.py`, na estrutura `PREMISSAS`, e são lidas de lá tanto pelo
pipeline quanto pelo relatório. Não existe premissa documentada em prosa que não esteja vigente na
execução. A tabela completa, com regra, motivo e alternativa rejeitada, está na seção 10 do
relatório. As de maior impacto:

| ID | Tema | Regra |
|---|---|---|
| P01 | Receita reconhecida | Rateio pro-rata diário sobre a competência |
| P02 | Elegibilidade | Exclui `CANCELADA`; inclui `ABERTA` e `VENCIDA`; nota de crédito com sinal invertido |
| P03 | Câmbio de fluxos | PTAX venda média do mês de competência |
| P04 | Câmbio de caixa | PTAX venda do dia da liquidação, com forward-fill |
| P05 | Deduplicação | `numero_fatura` é a chave; desempate determinístico |
| P06 | MRR | `seats × unit_price`, sem anualizar contrato anual |
| P08 | Identidade do cliente | Entidade econômica é o CNPJ, não o `customer_id` |
| P09 | COGS | Custo sem dono não é rateado |
| P10 | Canal | `PLG` e `Product-Led` são o mesmo; `Brand` só entra no CAC blended |
| P12 | LTV | Sobre margem bruta e churn de receita |

Duas premissas merecem destaque pelo raciocínio, não pelo impacto:

**P07** foi reescrita durante o desenvolvimento. A verificação inicial apontou cinco pares de
assinaturas sobrepostas no mesmo cliente, o que sugeria uma regra de truncamento de vigência.
Investigando, a sobreposição era artefato das próprias linhas duplicadas: o registro que sobrepunha
era ele mesmo. Depois da deduplicação não resta nenhuma sobreposição, então nenhuma regra de
truncamento foi criada. O teste que detectaria a necessidade continua no pipeline e falha se
sobreposição real aparecer em carga futura.

**P14** declara uma anomalia de impacto exatamente zero: quatro assinaturas com `billing_period`
nulo. Como `unit_price` é mensal nos dois ciclos, o campo não entra em nenhuma fórmula. Está
documentada para separar defeito de dado de defeito de métrica, e para que a anomalia não seja usada
para desqualificar um número que ela não afeta.

---

## Pergunta 7: como estas definições continuam valendo

Resposta completa na seção 9 do relatório. O resumo é que documentação e alinhamento não sobrevivem
a uma sexta-feira de fechamento, e o que sobrevive é mecanismo. Os cinco, na ordem de implantação, e
com indicação do que já está implementado:

1. **Definição como código.** As premissas estão em `src/config.py` e são lidas pelo pipeline e pelo
   relatório da mesma fonte. Mudar o texto sem mudar a regra é impossível, porque o texto é a regra.
   *Implementado.*
2. **Teste que derruba a publicação.** Vinte e seis verificações por execução. As de severidade
   `ERRO` encerram o processo com código diferente de zero e nada é publicado. Alterar a regra de
   MRR sem cuidado faz a decomposição deixar de fechar e o pipeline para. *Implementado.*
3. **Dono nomeado por definição.** Receita e receita diferida na Contabilidade; MRR, churn e NRR em
   Vendas; COGS e alocação de infra em Infra. Dono é quem aprova mudança, não quem calcula.
4. **Mudança de definição entra por pull request** que altera a premissa, o teste correspondente e
   uma nota de decisão com data, autor e motivo, aprovada pelo dono. O ganho prático é responder em
   segundos se o número mudou porque o negócio mudou ou porque a regra mudou.
5. **Camada de consumo única.** As áreas leem as tabelas `gold_*`, nunca as fontes cruas. Número que
   aparece em reunião e não existe na camada de consumo não é discutido, é virado em pedido de
   inclusão.

---

## Limitações conhecidas

- **Margem bruta cobre apenas custo de cloud.** Não há dados de suporte, folha técnica nem
  infraestrutura compartilhada de produto. A margem real é menor que a reportada, e o relatório diz
  isso explicitamente em vez de apresentar o número como margem bruta completa.
- **Metade do COGS não tem dono.** Enquanto a governança de tags não for corrigida, margem por
  cliente serve para priorizar investigação, não para decidir preço ou desligar cliente.
- **CAC sem defasagem.** O investimento é atribuído ao mês de aquisição, sem modelar o intervalo
  entre gasto e conversão. O último trimestre da janela tem denominador incompleto e CAC
  artificialmente alto.
- **LTV assume churn constante.** Em base com menos de cem clientes, um Enterprise que sai move o
  indicador do mês inteiro. A leitura válida do churn é anual, não mensal.
- **LTV/CAC de 14x não deve ser lido como eficiência.** Com payback de cinco meses, o mais provável
  é subinvestimento em aquisição ou churn subestimado pela janela curta de histórico.
- **Nove pagamentos órfãos** não têm fatura correspondente em nenhuma fonte. Entram no caixa e não
  podem ser atribuídos a cliente nem a competência.
- **Câmbio até a data de corte.** A série de MRR termina no último mês com cotação publicada. Sem
  isso, o MRR em dólar viraria nulo e desapareceria em silêncio da decomposição.

---

## O que eu faria com mais tempo

1. **Fechar a governança de tags do cloud**, que é o item de maior retorno analítico do projeto:
   desbloqueia metade do COGS e transforma margem por cliente em número acionável.
2. **Rotina de desprovisionamento acionada por churn.** Há clientes consumindo infraestrutura em
   meses sem nenhuma receita. É o único achado que devolve dinheiro sem depender de negociação com
   cliente nem de mudança de produto.
3. **Coorte de retenção de receita por mês de aquisição**, para separar o efeito de safra do efeito
   de época e responder se a piora do churn vem de safras recentes piores ou de deterioração da base
   inteira.
4. **Modelo de alocação de COGS por consumo real**, com `compute` alocado por uso e `storage` por
   volume, em vez do agregado por workspace, permitindo custo unitário por assento.
5. **Testes de unidade sobre as macros de coerção** de data e de valor monetário, com casos de borda
   propositais. Hoje elas são validadas indiretamente pelas reconciliações do resultado final.
6. **Defasagem de CAC**, atribuindo investimento à conversão com janela móvel, e CAC por segmento
   além de por canal.

---

## Escopo cortado

Duas coisas ficaram fora, com o motivo:

- **Dashboard interativo.** O entregável de visualização é o relatório HTML estático. Para uma
  audiência que precisa auditar número, reconciliação escrita vale mais que filtro clicável, e o
  arquivo abre em qualquer máquina sem servidor. As tabelas `gold_*` estão prontas para alimentar
  Streamlit ou Metabase sem retrabalho.
- **Orquestrador.** Não há Airflow nem Dagster porque o pipeline roda em segundos e o requisito é um
  comando. `run.py` já devolve código de saída adequado para agendamento, o que é o suficiente até
  existir dependência entre pipelines.
