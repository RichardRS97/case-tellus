# Resumo executivo

**Para:** Head of Finance, Tellus Tecnologia S.A.
**Assunto:** Unit economics de jan/2024 a jun/2026, e o que fazer a respeito
**Data de corte dos dados:** 15/07/2026 · **Moeda:** BRL

---

## 1. O número que reportamos hoje está certo por coincidência, não por controle

Somando as fontes como elas chegam, a receita do período é de **BRL 15.310.317**. Apurada
corretamente, é de **BRL 15.282.249**. A diferença é de BRL 28.069, ou 0,18%, e passaria em qualquer
revisão superficial.

Esse conforto é falso. A diferença pequena é resultado de **BRL 4.670.381 de erros brutos que se
anularam entre si**: documentos duplicados e notas de crédito somando em vez de subtrair empurravam a
receita para cima; faturas em dólar somadas como se fossem reais empurravam para baixo. Nenhum
controle produziu esse encontro, foi acaso aritmético. **Basta o dólar se mover ou o mix de clientes
internacionais mudar para o erro deixar de se cancelar e aparecer inteiro no resultado.**

Nas demais métricas não houve a mesma sorte, porque cada uma depende de um subconjunto diferente dos
mesmos defeitos:

| Métrica | Sem tratamento | Correto | Erro |
|---|---:|---:|---:|
| MRR em jun/2026 | BRL 2.523.848 | **BRL 729.265** | +246% |
| ARR em jun/2026 | BRL 30.286.176 | **BRL 8.751.182** | +246% |
| Custo de cloud do período | BRL 620.428 | **BRL 6.781.464** | −91% |
| Margem bruta do período | 96% | **55,6%** | +40 p.p. |
| CAC blended | BRL 20.284 | **BRL 39.773** | −49% |

O erro de 246% no MRR vem de uma única linha de raciocínio: multiplicar por doze o preço de
assinaturas anuais, quando o preço já é mensal. O erro de 91% no custo vem de somar dólar como real e
de um `JOIN` que descarta em silêncio metade dos servidores. **O ARR que a empresa acredita ter é
3,5 vezes o real.**

---

## 2. Metade do custo de servir não tem dono, e isso impede decisão de preço

Dos **BRL 6.781.464** de cloud no período, **52,8% não podem ser atribuídos a nenhum cliente**: 27
servidores sem nenhum responsável cadastrado e 3 apontando para duas empresas diferentes ao mesmo
tempo. São os servidores mais caros da operação, com custo médio quatro vezes maior que os demais.

Por isso este relatório apresenta **duas margens** em vez de uma:

- **Margem direta de 79,0%**, contando apenas o custo com dono identificado. É o piso otimista.
- **Margem consolidada de 55,6%**, contando todo o custo de servir. É o número real.

Optei deliberadamente por **não distribuir esse custo entre os clientes**. Distribuir produziria uma
margem por cliente com aparência de precisão e sem lastro nenhum, e essa margem seria usada para
definir preço e para decidir quem cortar. Enquanto a governança de identificação dos servidores não
for corrigida, **margem por cliente serve para priorizar investigação, não para decidir preço**.

Dentro do que já é possível medir, há um achado estrutural: o **plano Starter opera com 52,6% de
margem contra 83,3% do Enterprise**, com 34 clientes gerando apenas BRL 272 mil de receita. Existe um
piso de infraestrutura por cliente que não cai quando o preço cai. Starter não é um plano de entrada
barato, é um plano que consome margem enquanto o cliente não sobe de patamar.

---

## 3. Estamos pagando servidor de cliente que já foi embora

**BRL 561.644** foram gastos em infraestrutura de **37 clientes em meses nos quais eles não geraram
nenhuma receita**, a maioria já sem contrato ativo. São servidores de clientes que saíram e nunca
foram desligados. Isso equivale a **8,3% de todo o custo de cloud do período**.

É o único item deste relatório que devolve dinheiro **sem depender de negociar com cliente, mudar
preço ou alterar o produto**. Depende de uma rotina de desligamento disparada pelo evento de
cancelamento.

---

## O restante do quadro, em uma linha cada

- **Retenção de receita (NRR) de 103% em doze meses**, com retenção de clientes de 80%. A receita se
  manteve porque quem ficou expandiu, enquanto 9 clientes da base saíram. Isso é **concentração
  crescente**: a empresa está ficando mais dependente de menos clientes.
- **Churn piorou e estabilizou acima de 2024**, de 1,13% para 1,72% de clientes por mês. Com menos de
  cem clientes, um Enterprise que sai move o mês inteiro, então a leitura válida é anual.
- **Receita diferida de BRL 1.816.890** em 30/06/2026: serviço já cobrado e não entregue, com
  reconhecimento até jun/2027. É obrigação, não resultado.
- **Caixa superou a receita em BRL 384.857** no período, por contratos anuais cobrados de uma vez.
  Os dois números medem coisas diferentes e não deveriam ser iguais.
- **Product-Led paga o CAC em 1,9 mês; Inbound leva 8,4 meses.** Inbound custa BRL 67.707 por cliente
  contra BRL 15.688 do Product-Led, e traz menos clientes.
- **LTV/CAC de 14,2x não é conquista.** A referência saudável é de 3x a 5x. Com payback de 4,9 meses,
  o mais provável é subinvestimento em crescimento, não eficiência excepcional.

---

## As três decisões que peço

**1. Adotar as definições deste documento como as definições oficiais da empresa.**
Enquanto Vendas, Contabilidade e Infra mantiverem três planilhas, a discussão continuará sendo sobre
qual número está certo, e não sobre o que fazer com ele. O mecanismo proposto não é documentação, que
não sobrevive a uma sexta-feira de fechamento: as definições ficam em código, 26 verificações rodam a
cada execução, e as bloqueantes impedem a publicação. Alterar a regra de MRR sem cuidado faz a
decomposição deixar de fechar e o processo para antes de gerar número. Isso já está funcionando.

**2. Autorizar o desligamento da infraestrutura de clientes que já saíram.**
Retorno imediato de BRL 561.644 no horizonte medido, sem contrapartida comercial.

**3. Tratar a identificação de dono dos servidores como pré-requisito de qualquer decisão de
preço.** É o que desbloqueia metade do custo de servir e transforma margem por cliente em número
acionável. Sem isso, decisão de precificação estará sendo tomada sobre 79% de margem quando a
realidade é 55,6%.

---

*Base: 1.370 documentos fiscais após deduplicação (de 1.417 linhas no arquivo original), 212
assinaturas, 1.286 pagamentos, 10.632 registros de cloud e 94 entidades econômicas (de 100 cadastros).
Câmbio PTAX venda extraído da API de dados abertos do Banco Central. Todos os números deste resumo são
reproduzíveis por um comando e passaram por 26 verificações de reconciliação; rateio de competência,
decomposição de MRR e o encadeamento de erros da seção 1 fecham no centavo. Detalhamento, premissas e
trilha de auditoria no relatório completo (`out/relatorio_tellus.html`).*
