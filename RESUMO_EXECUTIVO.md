# Resumo executivo

**Para:** Head of Finance, Tellus Tecnologia S.A.
**Assunto:** Unit economics de jan/2024 a jun/2026, e o que fazer a respeito
**Data de corte dos dados:** 15/07/2026 · **Moeda:** BRL

---

## 1. O número que reportamos hoje está certo por coincidência, não por controle

Somando as fontes como elas chegam, a receita do período é de BRL 15.310.317. Apurada corretamente,
é de **BRL 15.282.249**. Diferença de 0,18%, que passaria em qualquer revisão superficial.

Esse conforto é falso. A diferença pequena é resultado de **BRL 4,67 milhões de erros brutos que se
anularam entre si**: duplicidade e nota de crédito somando em vez de subtrair empurravam a receita
para cima; fatura em dólar somada como se fosse real empurrava para baixo. Nenhum controle produziu
esse encontro, foi acaso aritmético. **Basta o dólar se mover para o erro deixar de se cancelar.**

Nas demais métricas não houve a mesma sorte:

| Métrica | Sem tratamento | Correto | Erro |
|---|---:|---:|---:|
| MRR / ARR em jun/2026 | BRL 2,52 mi / 30,3 mi | **BRL 729 mil / 8,75 mi** | +246% |
| Custo de cloud do período | BRL 620 mil | **BRL 6,78 mi** | −91% |
| Margem bruta do período | 96% | **55,6%** | +40 p.p. |

O MRR erra 246% por multiplicar por doze o preço de assinaturas anuais, quando o preço já é mensal.
**O ARR que a empresa acredita ter é 3,5 vezes o real.**

## 2. Metade do custo de servir não tem dono, e isso impede decisão de preço

Dos BRL 6,78 milhões de cloud no período, **52,8% não podem ser atribuídos a nenhum cliente**: 27
servidores sem responsável cadastrado e 3 apontando para duas empresas ao mesmo tempo. Por isso o
relatório traz **duas margens**: direta de 79,0% (só custo com dono, piso otimista) e consolidada de
55,6% (todo o custo, número real). Optei por **não ratear** esse custo: geraria margem por cliente com
precisão falsa, usada depois para decidir preço e corte.

## 3. Estamos pagando servidor de cliente que já foi embora

**BRL 561.644** em infraestrutura de **37 clientes em meses sem nenhuma receita**, a maioria já sem
contrato ativo. É o único item que devolve dinheiro **sem negociar com cliente, mudar preço ou
alterar produto** — só de uma rotina de desligamento disparada pelo cancelamento.

## O restante do quadro, em uma linha cada

- **NRR de 103% em 12 meses com retenção de clientes de só 80%.** Receita se manteve porque quem
  ficou expandiu; é **concentração crescente**, não saúde de carteira.
- **LTV/CAC de 14,2x não é conquista.** Referência saudável é 3x-5x; com payback de 4,9 meses, o mais
  provável é subinvestimento em crescimento, não eficiência.

## As três decisões que peço

**1. Adotar as definições deste documento como as definições oficiais da empresa.** Ficam em código,
com 26 verificações que impedem a publicação de número que contrarie a regra. Já está funcionando.

**2. Autorizar o desligamento da infraestrutura de clientes que já saíram.** Retorno imediato de
BRL 561.644, sem contrapartida comercial.

**3. Tratar identificação de dono dos servidores como pré-requisito de decisão de preço.**
Desbloqueia metade do custo de servir: sem isso, preço é decidido sobre 79% de margem quando a
realidade é 55,6%.

---

*Base: 1.370 documentos fiscais, 212 assinaturas, 1.286 pagamentos, 10.632 registros de cloud, 94
entidades. Câmbio PTAX via API do Banco Central. Reproduzível por um comando, 26 verificações de
reconciliação. Detalhamento completo em `out/relatorio_tellus.html`.*
