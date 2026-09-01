# Diário técnico do case Tellus

Este documento não é para o board, é para quem quer entender **como** se chegou aos números do
`RESUMO_EXECUTIVO.md` e do `out/relatorio_tellus.html`. É a jornada na ordem em que ela aconteceu,
com o raciocínio por trás de cada decisão. Se `README.md` responde "como rodar e quais são as
premissas", este documento responde "por que o projeto ficou com esta cara e não com outra".

---

## 1. O ponto de partida: não confiar em nada antes de olhar

Antes de escrever qualquer linha de transformação, a primeira pergunta não foi "como calculo MRR",
foi "o que tem de errado nestes arquivos que eu ainda não vi". Essa inversão de ordem é a decisão
mais importante do projeto inteiro, porque um pipeline bem escrito sobre premissa errada produz
número errado com aparência de rigor, que é o cenário mais perigoso em finanças.

**O que foi feito:** três scripts de investigação, hoje preservados em `analise_exploratoria/`,
antes de qualquer tabela silver existir.

- `00_inspeciona_sqlite.py`: abriu o `tellus_financeiro.db` só para ver schema e amostra.
- `01_auditoria_fontes.py`: passou por cada uma das cinco fontes contando duplicidade, tipo de
  dado, formato de data, nulos, negativos, e cruzou chaves entre fontes (cliente em fatura que não
  existe em customers, id_assinatura que não existe em assinaturas, etc.).
- `02_investiga_workspaces_e_bcb.py`: aprofundou dois achados específicos que a primeira auditoria
  levantou mas não explicou — os workspaces sem cliente mapeado, e validou os parâmetros reais da
  API do Banco Central antes de depender dela.
- `03_investiga_casos_borda_assinaturas.py`: fechou dúvidas pontuais sobre `assinaturas.jsonl` que
  mudariam a regra de negócio se respondidas errado (duplicidade é a mesma linha? a sobreposição de
  vigência é real ou artefato?).

**Por que isso importa para aprendizado:** cada arquivo `*.saida.txt` ao lado do script é a evidência
bruta que sustenta cada premissa do projeto. Se alguém perguntar "por que você decidiu que nota de
crédito está com sinal errado", a resposta não é opinião, é a linha exata da saída do script 01 que
mostra 35 notas de crédito com valor positivo. Auditoria sem evidência gravada é afirmação, não
diagnóstico.

### O que a auditoria mudou de decisão, na prática

Dois achados da investigação **mudaram uma regra depois de já estar desenhada**, e isso é mais
instrutivo do que os achados que confirmaram a intuição inicial:

- **A "sobreposição de assinaturas" não existia.** A leitura inicial de `assinaturas.jsonl` mostrou
  5 pares de assinaturas do mesmo cliente com vigência sobreposta, o que sugeria a necessidade de uma
  regra de truncamento (mudança de plano encerra a assinatura anterior). O script 03 investigou linha
  a linha e descobriu que os 6 `subscription_id` duplicados eram idênticos byte a byte, e a
  "sobreposição" era o próprio registro duplicado se sobrepondo a si mesmo. Depois de deduplicar,
  sobreposição real = zero. A regra de truncamento **não foi implementada**, porque implementá-la
  seria corrigir um problema que não existe e esconderia uma sobreposição real futura. Ficou só um
  teste que fica de vigia (`alerta_sobreposicao_vigencia` em `sql/30_silver_assinaturas.sql`).
- **Os workspaces sem cliente não eram ruído de cadastro.** A hipótese inicial, ao ver 27 workspaces
  sem dono, era "erro de digitação no mapa". O script 02 comparou o mix de serviço (compute, storage,
  egress, ai_tokens) e o custo médio desses workspaces contra os mapeados: mix idêntico, custo médio
  quatro vezes maior, presença nos 30 meses da série. Isso não é o perfil de um erro de digitação, é
  o perfil de infraestrutura de plataforma ou de um bloco de contas sem tag de dono. Essa distinção
  decidiu a premissa P09: não ratear esse custo por receita, porque ratear estaria disfarçando uma
  falha de governança como um número de negócio.

Esse é o padrão que vale levar para qualquer análise: **quando um achado parece estranho, ele merece
uma segunda pergunta antes de virar regra.** A primeira leitura de dado sujo costuma sugerir a
correção mais óbvia, e a correção mais óbvia costuma estar resolvendo o sintoma errado.

---

## 2. Por que a arquitetura ficou em camadas (bronze / silver / gold)

A decisão de separar em três camadas não veio de dogma de engenharia de dados, veio de uma
necessidade concreta deste case: **o enunciado pede que qualquer número seja rastreável até a fonte
crua**, e a pergunta 6 pede para listar exatamente o que está errado em cada fonte. As duas exigências
juntas eliminam a opção de transformar tudo em uma única passada.

- **Bronze** (`src/bronze.py`) existe para responder "o que a fonte realmente disse", sem nenhuma
  correção. Cada linha carrega o arquivo de origem, o encoding usado na leitura, o número da linha
  física e um hash do conteúdo. Isso parece excesso de engenharia até o momento em que alguém
  pergunta "de onde veio esse número de MRR" na defesa: sem essa linhagem, a resposta seria "confio
  no código", com linhagem a resposta é "linha 812 do CSV, aqui está o hash para confirmar que não foi
  alterado".
- **Silver** (`sql/20` a `sql/50`) é onde a bagunça é resolvida uma vez, em SQL versionado e testável,
  não espalhada em código Python difícil de auditar. Cada linha que não passa numa regra vai para uma
  tabela `quarentena_*` com o motivo escrito, nunca é silenciosamente descartada ou silenciosamente
  corrigida por adivinhação.
- **Gold** (`sql/60` a `sql/95`) é a única camada que qualquer área deveria consultar. A separação
  física entre "o que existe" e "o que se pode usar" é o que sustenta a proposta de governança da
  pergunta 7: se Vendas só pode ler `gold_mrr_mensal`, ela não tem como reinventar sua própria
  definição de MRR nem por acidente.

**Ferramenta escolhida:** DuckDB. A decisão foi de proporção, não de moda. O volume total do case é
de aproximadamente 13 mil linhas somando as cinco fontes. Um Postgres, um Spark, um dbt com warehouse
cloud seriam infraestrutura desproporcional ao problema, e o enunciado pede explicitamente "um comando
roda tudo do zero, de forma reprodutível". DuckDB dá SQL analítico completo (`QUALIFY`, `FILTER`,
funções de janela, `generate_series` para expandir competência dia a dia) dentro de um arquivo local,
sem servidor para configurar e sem dependência de rede além da API de câmbio. É a ferramenta que
desaparece do caminho entre a decisão de negócio e o SQL que a implementa.

**Por que SQL para a transformação e Python só para orquestração:** o enunciado pede "core em Python
e SQL" e deixa a engine livre. A escolha foi jogar a lógica de negócio inteira em SQL (é o que fica em
`sql/*.sql`) e usar Python só para três coisas que SQL não faz bem: buscar dados de uma API HTTP,
gerar a série de câmbio dia a dia, e orquestrar a ordem de execução. Isso importa para aprendizado
porque é uma escolha deliberada de onde cada linguagem é mais forte, e não simplesmente "eu sei mais
Python do que SQL" ou o inverso.

---

## 3. As duas peças de engenharia mais difíceis do projeto

### 3.1 O rateio pro-rata de receita por competência

Cinquenta e três documentos no `faturas_export.csv` cobrem mais de dois meses de competência, alguns
até treze meses (contrato anual cobrado de uma vez). Reconhecer o valor inteiro no mês da emissão
teria sido o caminho de menor esforço, e teria produzido picos de receita que não existem e um saldo
de receita diferida sem nenhum lastro.

A solução, em `sql/40_silver_faturas.sql`, expande cada documento em uma linha por mês de competência
usando `generate_series`, calcula quantos dias daquele mês o documento cobre, e rateia o valor
proporcionalmente aos dias. A parte que exigiu mais cuidado não foi o rateio em si, foi garantir que a
**soma das parcelas de um documento sempre devolva exatamente o valor original**, sem sobra nem falta
por arredondamento de data. Essa garantia é uma das 26 verificações bloqueantes
(`rateio_prorata_fecha` em `src/checks.py`): se algum dia um ajuste de código quebrar essa igualdade,
o pipeline para antes de publicar qualquer relatório.

### 3.2 A decomposição de MRR com efeito cambial isolado

Este foi o ponto onde a engenharia teve que servir a uma decisão de negócio explícita, não o
contrário. A pergunta 2 pede para decompor a variação do MRR em novo, expansão, contração e churn.
O problema é que a Tellus tem clientes contratando em dólar, e o dólar se move todo mês. Sem tratar
isso, um cliente que não comprou nem cancelou nada apareceria com "expansão" só porque o dólar subiu
naquele mês, e a diretoria comemoraria variação de câmbio como resultado comercial.

A solução foi uma identidade algébrica que separa os dois efeitos de forma exata, não aproximada:

```
MRR_t · FX_t − MRR_(t−1) · FX_(t−1)
  = (MRR_t − MRR_(t−1)) · FX_(t−1)     efeito de volume (novo/expansão/contração/churn)
  + MRR_t · (FX_t − FX_(t−1))          efeito cambial, isolado
```

Implementada em `sql/70_gold_mrr.sql`, essa fórmula garante que os componentes somem exatamente a
variação observada do MRR, sem resíduo. O resíduo é medido e verificado a cada execução
(`decomposicao_mrr_fecha`). Essa é a diferença entre "decompor um número" e "decompor um número de um
jeito que se pode provar que fecha".

---

## 4. Os bugs que o próprio pipeline pegou (a parte mais honesta do processo)

Vale registrar porque é a evidência de que o mecanismo de verificação funciona de verdade, e não é
teatro. Durante o desenvolvimento, os 26 checks bloqueantes pegaram quatro erros que estavam no
código, não nos dados:

1. **Câmbio errado por moeda ausente.** Nos meses em que uma entidade não tinha MRR, a coluna de
   moeda ficava nula, e o join de câmbio aplicava a taxa do dólar a um cliente que fatura em real.
   Corrigido tratando a moeda como atributo fixo da entidade (`dim_entidade_moeda`), nunca deduzida
   linha a linha.
2. **MRR em dólar desaparecendo da série.** A grade de meses ia além do último mês com cotação
   publicada pelo Banco Central, e sem cotação o MRR em USD virava nulo e simplesmente desaparecia da
   decomposição, sem erro visível. Corrigido limitando a grade ao intervalo real de cobertura do
   câmbio (`dim_horizonte`).
3. **Fan-out de join duplicando custo.** Um workspace pode pertencer a mais de um cliente na fonte
   crua (não é erro de digitação, é conflito de atribuição real, ver seção 1). Juntar direto sem tratar
   isso multiplicava o custo pelo número de "donos" declarados.
4. **Divisão inteira gerando coorte fracionária.** Um cálculo de trimestre em SQL devolveu literalmente
   `2024-T1.3333333333333333`, porque a divisão entre inteiros no DuckDB retorna float sem casting
   explícito.

Nenhum desses quatro foi encontrado por revisão visual de código, foi a verificação de reconciliação
falhando com um número que não fechava. É o argumento mais forte a favor de escrever o teste antes de
confiar no resultado: revisão de código encontra o que o revisor já sabe procurar, o teste de
reconciliação encontra o que ninguém pensou em procurar.

---

## 5. Como as conclusões de negócio nasceram dos números, não o contrário

A ordem real de trabalho foi: rodar o pipeline até ele passar em todas as verificações, **depois**
olhar os resultados brutos em `tests/imprime_resultados.py`, e só então decidir qual é a história que
os números contam. Isso é importante porque a ordem inversa (decidir a história antes de calcular)
é o caminho mais curto para confirmar viés.

Três conclusões nasceram assim, direto da tabela de resultado, sem terem sido hipótese de partida:

- **O erro líquido pequeno escondendo erro bruto grande** só ficou visível depois de montar o
  `gold_bridge_receita` (`sql/95_naive.sql`) e ver que a soma dos ajustes com valor absoluto era vinte
  vezes maior que a diferença final. Sem construir o bridge com cada erro isolado, o relatório teria
  dito só "a receita bate, diferença de 0,18%", que é verdade e é a conclusão errada de se tirar.
- **A infraestrutura de cliente que já saiu** (BRL 561.644 em 37 clientes sem receita no mês) surgiu
  de uma pergunta que não estava em nenhuma das sete perguntas do enunciado: "existe custo de cloud em
  cliente que não gerou receita naquele mês?". Foi escrita como consulta ad hoc depois de já ter a
  margem por cliente pronta, porque a tabela de margem deixou visível que havia entidades com COGS e
  receita zero.
- **A concentração crescente por trás de um NRR aparentemente bom** (103% de retenção de receita
  com só 80% de retenção de clientes) só apareceu ao colocar as duas métricas lado a lado na mesma
  tabela. Isoladamente, cada uma conta uma história tranquilizadora.

A lição de método aqui é: depois que o pipeline garante que os números estão certos, o trabalho de
análise é olhar a tabela de resultado inteira, não só as células que respondem diretamente à pergunta
que foi feita.

---

## 6. Por que o relatório final é um HTML sem nenhuma dependência externa

Esta foi uma decisão condicionada por uma restrição do usuário: nenhum arquivo deste projeto poderia
tocar a plataforma Snowflake nem depender de qualquer serviço externo além da API de câmbio exigida
pelo enunciado. Isso descartou de imediato qualquer biblioteca de gráfico via CDN e qualquer dashboard
que precisasse de servidor.

A solução em `src/viz.py` gera os seis gráficos do relatório como **SVG puro, construído em Python com
coordenadas calculadas manualmente**, sem nenhuma biblioteca de visualização. É mais trabalho do que
chamar uma função de gráfico pronta, mas o resultado abre em qualquer navegador, em qualquer máquina,
sem internet, com duplo clique. Para um relatório que vai para C-levels e depois vai para uma defesa
técnica de 45 minutos, essa portabilidade tem valor maior que a conveniência de usar Chart.js.

A escolha do **waterfall** (gráfico de cascata) para o bridge de erro na seção 2 do relatório não foi
estética, foi funcional: é o único tipo de gráfico que mostra, na mesma imagem, o ponto de partida, o
efeito individual de cada erro (com direção, positiva ou negativa) e o ponto de chegada, permitindo
que quem olha veja em três segundos que há mais movimento embaixo do capô do que a diferença final
sugere. Um gráfico de barras simples com "antes" e "depois" teria escondido exatamente o argumento
mais importante do relatório.

---

## 7. Onde está cada coisa, e o que ler para aprender o quê

| Se você quer entender... | Leia |
|---|---|
| A conclusão para quem decide, em 1 página | `RESUMO_EXECUTIVO.md` |
| O relatório completo, com todos os gráficos e tabelas | `out/relatorio_tellus.html` |
| Como rodar e a lista fechada de premissas | `README.md` |
| A evidência bruta de cada defeito de dado encontrado | `analise_exploratoria/*.saida.txt` |
| A lógica de negócio de cada indicador, em SQL legível | `sql/*.sql`, na ordem numérica |
| As 15 premissas como código, não como texto | `src/config.py`, dicionário `PREMISSAS` |
| O que pode derrubar a publicação de um número | `src/checks.py` |
| Como os gráficos são desenhados sem nenhuma biblioteca | `src/viz.py` |
| Como tudo se conecta, do comando único ao arquivo final | `run.py` e `src/pipeline.py` |

**Uma leitura sugerida para quem está aprendendo com este projeto:** primeiro o `RESUMO_EXECUTIVO.md`
para entender o que foi entregue e por quê; depois este documento, para entender a jornada; depois
`sql/40_silver_faturas.sql` e `sql/70_gold_mrr.sql`, que são as duas peças de engenharia mais densas;
por fim `src/checks.py`, que é o que transforma tudo isso de "código que parece certo" em "código que
prova que está certo".
