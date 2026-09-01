"""Monta o relatorio executivo em HTML autocontido, sem dependencia externa."""
from __future__ import annotations

import logging
from datetime import datetime

import duckdb

import viz
from config import DATA_CORTE, OUT_DIR, PERIODO_FIM, PERIODO_INI, PREMISSAS
from viz import brl, esc, num, pct, tabela

log = logging.getLogger(__name__)

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif; max-width: 1080px; width: 100%;
       margin: 0 auto; padding: clamp(14px, 3.5vw, 30px); line-height: 1.55;
       color: light-dark(#111827, #e5e7eb); background: light-dark(#ffffff, #0b1120); }
h1 { font-size: clamp(1.5rem, 4vw, 2.1rem); margin: 0 0 4px; letter-spacing: -0.02em;
     color: light-dark(#0f172a, #f1f5f9); }
h2 { font-size: clamp(1.15rem, 3vw, 1.4rem); margin: 44px 0 6px; padding-bottom: 7px;
     border-bottom: 2px solid light-dark(#e5e7eb, #1f2937); color: light-dark(#0f172a, #f1f5f9); }
h3 { font-size: 1.03rem; margin: 26px 0 6px; color: light-dark(#0f172a, #f1f5f9); }
.sub { color: light-dark(#6b7280, #9ca3af); font-size: 0.9rem; margin: 0 0 6px; }
p { margin: 9px 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }
.kpi { border: 1px solid light-dark(#e5e7eb, #1f2937); border-radius: 10px; padding: 13px 15px;
       background: light-dark(#f9fafb, #111827); }
.kpi .rot { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em;
            color: light-dark(#6b7280, #9ca3af); }
.kpi .val { font-size: 1.42rem; font-weight: 660; margin-top: 3px; letter-spacing: -0.02em; }
.kpi .obs { font-size: 0.79rem; color: light-dark(#6b7280, #9ca3af); margin-top: 3px; }
.table-wrap { overflow-x: auto; margin: 14px 0; }
table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
th, td { border: 1px solid light-dark(#e5e7eb, #263449); padding: 7px 10px; text-align: left;
         white-space: nowrap; }
th { background: light-dark(#f3f4f6, #172033); font-weight: 620; font-size: 0.8rem; }
td.dir, th.dir { text-align: right; font-variant-numeric: tabular-nums; }
tr.neg td { background: light-dark(#fef2f2, #2a1216); }
.card { border: 1px solid light-dark(#e5e7eb, #1f2937); border-radius: 10px; padding: 15px 18px;
        margin: 16px 0; background: light-dark(#f9fafb, #111827); }
.alerta { border-left: 4px solid #d97706; background: light-dark(#fffbeb, #26190a); }
.critico { border-left: 4px solid #dc2626; background: light-dark(#fef2f2, #2a1216); }
.ok { border-left: 4px solid #059669; background: light-dark(#ecfdf5, #062c22); }
.chart { margin: 16px 0; overflow-x: auto; }
.tag { display: inline-block; font-size: 0.7rem; font-weight: 650; padding: 2px 7px; border-radius: 5px;
       background: light-dark(#e0e7ff, #1e2a4a); color: light-dark(#3730a3, #a5b4fc); margin-right: 6px; }
.tag.err { background: light-dark(#fee2e2, #3f1517); color: light-dark(#991b1b, #fca5a5); }
.tag.ok { background: light-dark(#d1fae5, #06301f); color: light-dark(#065f46, #6ee7b7); }
code { font-family: ui-monospace, Consolas, monospace; font-size: 0.85em;
       background: light-dark(#f3f4f6, #1f2937); padding: 1px 5px; border-radius: 4px; }
ul, ol { margin: 9px 0; padding-left: 22px; }
li { margin: 5px 0; }
footer { margin-top: 50px; padding-top: 14px; border-top: 1px solid light-dark(#e5e7eb, #1f2937);
         font-size: 0.8rem; color: light-dark(#6b7280, #9ca3af); }
.dois { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
"""


def gerar(con: duckdb.DuckDBPyConnection, rel) -> str:
    def df(sql):
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def um(sql):
        r = con.execute(sql).fetchone()
        return r[0] if r else None

    log.info("montando relatorio executivo")
    p = []
    a = p.append

    # ------------------------------------------------------------ dados
    comp = df("SELECT * FROM gold_comparativo_metricas ORDER BY ordem")
    bridge = df("SELECT * FROM gold_bridge_receita ORDER BY ordem")
    rc = df("SELECT * FROM gold_receita_vs_caixa ORDER BY mes")
    mrr = df("SELECT * FROM gold_mrr_mensal WHERE mes BETWEEN "
             f"'{PERIODO_INI:%Y-%m}' AND '{PERIODO_FIM:%Y-%m}' ORDER BY ordem_mes")
    marg = df("SELECT * FROM gold_margem_mensal ORDER BY mes")
    plano = df("SELECT * FROM gold_margem_por_plano ORDER BY receita_brl DESC")
    nrr = df("SELECT * FROM gold_nrr_12m")[0]
    churn = df("SELECT * FROM gold_churn_tendencia ORDER BY ano")
    ue = df("SELECT * FROM gold_unit_economics")[0]
    cacc = df("SELECT * FROM gold_cac_por_canal ORDER BY spend_brl DESC")
    cacb = df("SELECT * FROM gold_cac_blended")[0]
    coorte = df("SELECT * FROM gold_cac_por_coorte ORDER BY coorte")
    payb = df("SELECT * FROM gold_payback_por_canal ORDER BY payback_meses")
    dif = df("SELECT * FROM gold_receita_diferida_fechamento")[0]
    difm = df("SELECT * FROM gold_receita_diferida_por_mes_futuro ORDER BY mes")
    naoatr = df("""SELECT motivo, count(DISTINCT workspace_id) ws, sum(custo_usd) usd, sum(custo_brl) brl
                   FROM silver_cogs_nao_atribuivel GROUP BY 1 ORDER BY brl DESC""")
    piores = df("""SELECT * FROM gold_margem_por_cliente
                   WHERE NOT sem_custo_atribuido ORDER BY margem_direta_brl LIMIT 12""")
    disp = df("""SELECT receita_periodo_brl r, margem_direta_brl m, nome_fantasia n
                 FROM gold_margem_por_cliente WHERE NOT sem_custo_atribuido""")

    # infra de cliente sem receita: dinheiro queimado sem contrapartida
    zumbi = df("""
        SELECT c.entidade_id, e.nome_fantasia, sum(c.cogs_brl) cogs_brl
        FROM gold_cogs_entidade_mes c
        JOIN silver_entidades e USING (entidade_id)
        LEFT JOIN gold_receita_entidade_mes r ON r.entidade_id = c.entidade_id AND r.mes = c.mes
        JOIN seed_dim_mes d ON d.mes = c.mes AND d.dentro_da_janela
        WHERE coalesce(r.receita_brl, 0) = 0
        GROUP BY 1, 2 HAVING sum(c.cogs_brl) > 0 ORDER BY cogs_brl DESC""")
    zumbi_total = sum(z["cogs_brl"] for z in zumbi)

    tot_rec = um("SELECT sum(receita_reconhecida_brl) FROM gold_receita_vs_caixa")
    tot_cx = um("SELECT sum(caixa_liquido_brl) FROM gold_receita_vs_caixa")
    erro_bruto = sum(abs(b["valor_brl"]) for b in bridge if b["papel"] == "ajuste")
    erro_liq = bridge[-1]["valor_brl"] - bridge[0]["valor_brl"]
    mrr_fim = mrr[-1]
    cogs_nao_atr_pct = um("""SELECT sum(cogs_nao_atribuivel_brl)/sum(cogs_total_brl) FROM gold_margem_mensal""")
    q_cli = df("""SELECT count(*) t, count(*) FILTER (WHERE destroi_valor) d,
                         count(*) FILTER (WHERE sem_custo_atribuido) s
                  FROM gold_margem_por_cliente""")[0]

    # ------------------------------------------------------------ cabecalho
    a(f"""<h1>Tellus Tecnologia | Unit Economics</h1>
<p class="sub">Periodo analisado: {PERIODO_INI:%b/%Y} a {PERIODO_FIM:%b/%Y} &nbsp;·&nbsp;
Moeda de reporte: BRL &nbsp;·&nbsp; Data de corte: {DATA_CORTE:%d/%m/%Y} &nbsp;·&nbsp;
Gerado em {datetime.now():%d/%m/%Y %H:%M}</p>""")

    # ------------------------------------------------------------ sumario executivo
    a("<h2>Sumario executivo</h2>")
    a(f"""<div class="card critico">
<p><strong>O numero de receita que a Tellus reporta hoje esta certo por coincidencia, nao por controle.</strong>
Somando as fontes sem tratamento chega-se a BRL {brl(bridge[0]['valor_brl'])} de receita no periodo, contra
BRL {brl(bridge[-1]['valor_brl'])} apurados corretamente. A diferenca liquida e de apenas
BRL {brl(abs(erro_liq))} ({pct(abs(erro_liq)/bridge[-1]['valor_brl'], 2)}), o que passaria em qualquer
revisao superficial.</p>
<p>Esse conforto e falso. A diferenca liquida pequena e resultado de <strong>BRL {brl(erro_bruto)} de erros
brutos que se anularam entre si</strong>: duplicidade e nota de credito empurravam a receita para cima,
a falta de conversao de dolar empurrava para baixo. Nenhum controle produziu esse encontro. Basta o mix de
clientes em USD mudar, ou o dolar se mover, para o erro deixar de se cancelar e aparecer inteiro no
resultado.</p></div>""")

    a(f"""<div class="kpis">
<div class="kpi"><div class="rot">Receita reconhecida</div><div class="val">{brl(tot_rec)}</div>
<div class="obs">competencia, {PERIODO_INI:%m/%Y} a {PERIODO_FIM:%m/%Y}</div></div>
<div class="kpi"><div class="rot">MRR em {mrr_fim['mes']}</div><div class="val">{brl(mrr_fim['mrr_brl'])}</div>
<div class="obs">ARR de {brl(mrr_fim['arr_brl'])}</div></div>
<div class="kpi"><div class="rot">Margem bruta consolidada</div>
<div class="val">{pct(um('SELECT 1 - sum(cogs_total_brl)/sum(receita_brl) FROM gold_margem_mensal'))}</div>
<div class="obs">{pct(um('SELECT 1 - sum(cogs_atribuivel_brl)/sum(receita_brl) FROM gold_margem_mensal'))} se olhar so o custo com dono</div></div>
<div class="kpi"><div class="rot">NRR 12 meses</div><div class="val">{pct(nrr['nrr_brl'])}</div>
<div class="obs">{pct(nrr['retencao_logica'])} de retencao de clientes</div></div>
<div class="kpi"><div class="rot">CAC blended</div><div class="val">{brl(cacb['cac_blended_brl'])}</div>
<div class="obs">payback de {num(ue['payback_meses'])} meses</div></div>
<div class="kpi"><div class="rot">COGS sem dono</div><div class="val">{pct(cogs_nao_atr_pct)}</div>
<div class="obs">nao e rateado neste relatorio</div></div>
</div>""")

    a("""<div class="card"><h3 style="margin-top:0">As tres coisas que o Head of Finance precisa decidir</h3>
<ol>
<li><strong>Aceitar as definicoes deste documento como as definicoes oficiais da empresa.</strong>
Enquanto Vendas, Contabilidade e Infra mantiverem tres planilhas, a discussao continuara sendo sobre qual
numero esta certo, e nao sobre o que fazer com ele. A Pergunta 7 propoe o mecanismo, com dono e com o
ponto exato onde o pipeline para de rodar se alguem contrariar a regra.</li>
<li><strong>Resolver a governanca de tags do cloud antes de usar margem por cliente para decidir preco.</strong>
Metade do custo de servir nao tem dono identificado. Nenhuma decisao de precificacao ou de corte de cliente
deve ser tomada sobre a margem direta enquanto isso nao for corrigido.</li>
<li><strong>Aprovar o desligamento da infraestrutura de clientes que ja sairam.</strong>
E o unico item desta lista que devolve dinheiro sem depender de negociacao com cliente nem de mudanca de
produto.</li>
</ol></div>""")

    # ---------------------------------------------------------- Pergunta 1
    a("<h2>Pergunta 1 &middot; Receita reconhecida x receita em caixa</h2>")
    a("<p class='sub'>Qual foi a receita reconhecida por mes em BRL, quanto entrou de caixa em cada mes, por que os dois numeros diferem e qual o saldo de receita diferida no fechamento de junho/2026.</p>")
    a('<div class="chart">' + viz.svg_linhas(
        [("Receita reconhecida (competencia)", [r["receita_reconhecida_brl"] for r in rc], viz.AZUL),
         ("Caixa liquido recebido", [r["caixa_liquido_brl"] for r in rc], viz.VERDE)],
        [r["mes"] for r in rc]) + "</div>")
    a(f"""<p>No periodo, entraram BRL {brl(tot_cx)} de caixa contra BRL {brl(tot_rec)} de receita
reconhecida, uma diferenca de BRL {brl(tot_cx - tot_rec)}. Os dois numeros medem coisas diferentes e nao
deveriam ser iguais. A diferenca tem quatro origens, todas identificadas:</p>
<ul>
<li><strong>Contratos anuais cobrados de uma vez.</strong> O caixa entra em um mes e a receita e reconhecida
ao longo de ate 13 meses. E a maior fonte de descolamento e a razao pela qual meses de venda anual mostram
caixa muito acima da receita.</li>
<li><strong>Prazo de recebimento.</strong> A fatura e reconhecida na competencia e liquidada depois, o que
desloca o caixa para a frente sem alterar a receita.</li>
<li><strong>Inadimplencia.</strong> Documentos com status VENCIDA geram receita reconhecida e nenhum caixa,
por escolha explicita de premissa: inadimplencia e perda de credito, nao ausencia de venda.</li>
<li><strong>Caixa nao reconciliado.</strong> {um('SELECT count(*) FROM alerta_pagamentos_orfaos')} pagamentos,
somando BRL {brl(um('SELECT sum(valor_brl) FROM alerta_pagamentos_orfaos'))}, nao tem fatura correspondente
em nenhuma fonte. Entram no caixa e nao podem ser atribuidos a cliente nem a competencia.</li>
</ul>""")
    a(f"""<div class="card alerta"><p><strong>Receita diferida em {PERIODO_FIM:%d/%m/%Y}:
BRL {brl(dif['saldo_diferido_brl'])}</strong>, distribuida em {dif['documentos_com_saldo']} documentos de
{dif['entidades']} clientes, com reconhecimento previsto de {dif['primeiro_mes']} a {dif['ultimo_mes']}.
E servico ja cobrado e ainda nao entregue: obrigacao de performance, nao resultado. Corresponde a
{pct(dif['saldo_diferido_brl']/tot_rec)} da receita reconhecida de todo o periodo analisado.</p></div>""")
    a(tabela(["Mes de competencia futura", "Receita a reconhecer (BRL)"],
             [[m["mes"], brl(m["receita_a_reconhecer_brl"])] for m in difm], alinhar_dir={1}))

    # ---------------------------------------------------------- Pergunta 2
    a("<h2>Pergunta 2 &middot; MRR, ARR e Net Revenue Retention</h2>")
    a("<p class='sub'>MRR e ARR no fechamento de cada mes, decomposicao da variacao mes a mes em novo, expansao, contracao, churn e efeito cambial, e NRR de 12 meses.</p>")
    a("""<p>As barras decompoem a variacao do MRR mes a mes e a linha azul e o MRR de fechamento. A
decomposicao inclui uma componente que a maioria dos relatorios omite: <strong>efeito cambial</strong>.
Sem separa-la, a valorizacao do dolar apareceria como expansao de receita em clientes que nao compraram
nenhum assento novo, e a diretoria comemoraria variacao de moeda como desempenho comercial.</p>""")
    a('<div class="chart">' + viz.svg_barras_empilhadas(
        [m["mes"] for m in mrr],
        [("Novo", [m["novo_brl"] for m in mrr], viz.VERDE),
         ("Expansao", [m["expansao_brl"] for m in mrr], "#34d399"),
         ("Reativacao", [m["reativacao_brl"] for m in mrr], viz.ROXO),
         ("Contracao", [m["contracao_brl"] for m in mrr], viz.AMBAR),
         ("Churn", [m["churn_brl"] for m in mrr], viz.VERMELHO),
         ("Cambio", [m["efeito_cambio_brl"] for m in mrr], viz.CINZA)],
        linha=("MRR de fechamento", [m["mrr_brl"] for m in mrr], viz.AZUL)) + "</div>")
    a(tabela(
        ["Mes", "MRR", "Variacao", "Novo", "Expansao", "Contracao", "Churn", "Cambio", "Clientes", "Residuo"],
        [[m["mes"], brl(m["mrr_brl"]), brl(m["variacao_brl"]), brl(m["novo_brl"]), brl(m["expansao_brl"]),
          brl(m["contracao_brl"]), brl(m["churn_brl"]), brl(m["efeito_cambio_brl"]),
          num(m["clientes_ativos"], 0), num(m["residuo_decomposicao_brl"], 2)] for m in mrr[-13:]],
        alinhar_dir=set(range(1, 10))))
    a(f"""<div class="card ok"><p><strong>Prova de fechamento.</strong> A coluna de residuo e a diferenca
entre a variacao observada do MRR e a soma dos componentes. Ela e zero em todos os meses porque a
decomposicao usa uma identidade algebrica exata, e nao uma atribuicao aproximada. Se algum dia deixar de
fechar, o pipeline para antes de publicar.</p></div>""")
    a(f"""<p><strong>NRR de 12 meses ({nrr['mes_ini']} a {nrr['mes_fim']}): {pct(nrr['nrr_brl'])}.</strong>
A coorte de {nrr['entidades_na_coorte']} clientes que existia no inicio da janela saiu de
BRL {brl(nrr['mrr_inicial_brl'])} para BRL {brl(nrr['mrr_final_brl'])} de MRR. Em moeda constante, isto e,
removendo o efeito do dolar, a NRR e {pct(nrr['nrr_moeda_constante'])}. A base perdeu
{nrr['entidades_perdidas']} clientes ({pct(1-nrr['retencao_logica'])} da coorte), e a receita se manteve
porque quem ficou expandiu. Retencao de receita acima de 100% com retencao de clientes de
{pct(nrr['retencao_logica'])} significa concentracao crescente: a empresa esta ficando mais dependente de
menos clientes.</p>""")

    # ---------------------------------------------------------- Pergunta 3
    a("<h2>Pergunta 3 &middot; Churn</h2>")
    a("<p class='sub'>Quanto a Tellus perde por churn e se a situacao esta melhorando ou piorando.</p>")
    a(tabela(
        ["Ano", "Clientes perdidos", "MRR perdido (BRL)", "Churn de clientes (mes)",
         "Churn de receita (mes)", "Churn de receita anualizado", "NRR media (mes)"],
        [[c["ano"], num(c["clientes_perdidos"], 0), brl(c["mrr_perdido_brl"]),
          pct(c["logo_churn_medio_mensal"], 2), pct(c["revenue_churn_medio_mensal"], 2),
          pct(c["revenue_churn_anualizado"]), pct(c["nrr_medio_mensal"])] for c in churn],
        alinhar_dir={1, 2, 3, 4, 5, 6}))
    pior = max(churn, key=lambda c: c["mrr_perdido_brl"])
    a(f"""<p>A resposta honesta e que <strong>a situacao piorou e depois estabilizou em um patamar mais alto
do que o de 2024</strong>. O churn de clientes subiu de {pct(churn[0]['logo_churn_medio_mensal'], 2)} ao mes
em 2024 para {pct(churn[-1]['logo_churn_medio_mensal'], 2)} em 2026. O ano mais dolorido foi
{pior['ano']}, com BRL {brl(pior['mrr_perdido_brl'])} de MRR perdido.</p>
<p>A anualizacao usa capitalizacao composta, nao multiplicacao por 12: perder
{pct(churn[-1]['revenue_churn_medio_mensal'], 2)} ao mes equivale a
{pct(churn[-1]['revenue_churn_anualizado'])} ao ano, e nao ao produto simples. Confundir os dois e o erro
mais comum em apresentacao de churn e superestima a perda.</p>
<p>Ressalva de leitura obrigatoria: a base tem menos de 100 clientes, portanto <strong>um unico cliente
Enterprise que sai move o indicador do mes inteiro</strong>. O churn mensal desta empresa nao deve ser lido
como tendencia; a leitura valida e a anual.</p>""")

    # ---------------------------------------------------------- Pergunta 4
    a("<h2>Pergunta 4 &middot; Margem bruta</h2>")
    a("<p class='sub'>Margem bruta por mes, por plano e por cliente, com a trajetoria da margem e o que a explica.</p>")
    a('<div class="chart">' + viz.svg_linhas(
        [("Margem direta (so custo com dono)", [m["margem_direta_pct"] for m in marg], viz.VERDE),
         ("Margem consolidada (todo o custo)", [m["margem_consolidada_pct"] for m in marg], viz.AZUL)],
        [m["mes"] for m in marg], formatador=lambda v: pct(v, 0)) + "</div>")
    a(f"""<div class="card critico"><p><strong>Existem duas margens porque metade do custo de servir nao tem
dono.</strong> Dos BRL {brl(um('SELECT sum(cogs_total_brl) FROM gold_margem_mensal'))} de cloud no periodo,
{pct(cogs_nao_atr_pct)} nao podem ser atribuidos a nenhum cliente. Isso produz a diferenca entre a margem
direta de {pct(um('SELECT 1 - sum(cogs_atribuivel_brl)/sum(receita_brl) FROM gold_margem_mensal'))} e a
consolidada de {pct(um('SELECT 1 - sum(cogs_total_brl)/sum(receita_brl) FROM gold_margem_mensal'))}.</p>
<p>Optei por <strong>nao ratear esse custo por receita</strong>. Ratear produziria uma margem por cliente
com aparencia de precisao e sem lastro: converteria uma falha de governanca de tags em numero, e esse numero
seria usado para decidir preco e corte de cliente. A margem direta e o piso confiavel, a consolidada e o
teto, e a decisao gerencial deve ser tomada sabendo que a verdade esta entre as duas.</p></div>""")
    a(tabela(["Motivo pelo qual o custo nao tem dono", "Workspaces", "USD", "BRL"],
             [[esc(n["motivo"]), num(n["ws"], 0), brl(n["usd"]), brl(n["brl"])] for n in naoatr],
             alinhar_dir={1, 2, 3}))

    a("<h3>Margem por plano</h3>")
    a(tabela(["Plano", "Receita (BRL)", "COGS atribuivel (BRL)", "Margem direta", "Clientes"],
             [[esc(x["plano"]), brl(x["receita_brl"]), brl(x["cogs_atribuivel_brl"]),
               pct(x["margem_direta_pct"]), num(x["entidades"], 0)] for x in plano],
             alinhar_dir={1, 2, 3, 4}))
    st = next((x for x in plano if x["plano"] == "Starter"), None)
    en = next((x for x in plano if x["plano"] == "Enterprise"), None)
    if st and en:
        a(f"""<p>O achado estrutural e o <strong>plano Starter</strong>: margem direta de
{pct(st['margem_direta_pct'])} contra {pct(en['margem_direta_pct'])} do Enterprise, com
{num(st['entidades'],0)} clientes gerando apenas BRL {brl(st['receita_brl'])} de receita. O custo de servir
nao cai na mesma proporcao do preco, porque ha um piso de infraestrutura por workspace que independe do
numero de assentos. Starter nao e um plano de entrada barato: e um plano que consome margem enquanto o
cliente nao sobe de patamar.</p>""")

    a("<h3>Quem da e quem nao da lucro</h3>")
    a("""<p>Cada ponto e um cliente. Acima da linha vermelha o cliente paga o proprio custo de
infraestrutura; abaixo, nao paga.</p>""")
    a('<div class="chart">' + viz.svg_dispersao(
        [(d["r"] or 0, d["m"] or 0, d["n"]) for d in disp]) + "</div>")
    a(f"""<p>De {num(q_cli['t'],0)} clientes, <strong>{num(q_cli['d'],0)} operam com margem direta
negativa</strong> e {num(q_cli['s'],0)} nao tem nenhum custo de cloud atribuido, o que os torna nao
avaliaveis ate a correcao das tags.</p>""")
    a(tabela(["Cliente", "Plano atual", "Receita (BRL)", "COGS (BRL)", "Margem (BRL)", "Margem %"],
             [[esc(x["nome_fantasia"]), esc(x["plano_atual"]), brl(x["receita_periodo_brl"]),
               brl(x["cogs_atribuivel_brl"]), brl(x["margem_direta_brl"]),
               pct(x["margem_direta_pct"]) if x["margem_direta_pct"] is not None else "n/d"]
              for x in piores],
             alinhar_dir={2, 3, 4, 5},
             destaque=lambda n, l: (piores[n]["margem_direta_brl"] or 0) < 0))
    if zumbi:
        a(f"""<div class="card critico"><p><strong>Dinheiro queimado sem contrapartida:
BRL {brl(zumbi_total)}.</strong> {len(zumbi)} clientes consumiram infraestrutura em meses em que nao
geraram nenhuma receita, quase todos ja sem assinatura vigente. Isso e workspace de cliente que saiu e
nunca foi desprovisionado.</p>
<p>E o item de maior retorno imediato deste relatorio, porque nao depende de renegociar contrato, mudar
preco nem alterar produto: depende de uma rotina de desprovisionamento acionada pelo evento de churn.
Os quatro maiores casos concentram BRL {brl(sum(z['cogs_brl'] for z in zumbi[:4]))}.</p></div>""")
        a(tabela(["Cliente sem receita no mes", "Custo de cloud consumido (BRL)"],
                 [[esc(z["nome_fantasia"]), brl(z["cogs_brl"])] for z in zumbi[:10]], alinhar_dir={1}))

    # ---------------------------------------------------------- Pergunta 5
    a("<h2>Pergunta 5 &middot; CAC, payback e LTV</h2>")
    a("<p class='sub'>Quanto custa adquirir um cliente por coorte e por canal, em quanto tempo esse custo se paga, LTV e a razao LTV/CAC.</p>")
    a(tabela(["Canal", "Investimento (BRL)", "Clientes adquiridos", "CAC (BRL)", "Payback (meses)", "LTV/CAC"],
             [[esc(c["canal"]), brl(c["spend_brl"]), num(c["novos_clientes"], 0),
               brl(c["cac_brl"]) if c["cac_brl"] else "nao atribuivel",
               num(next((x["payback_meses"] for x in payb if x["canal"] == c["canal"]), None)),
               num(next((x["ltv_cac"] for x in payb if x["canal"] == c["canal"]), None), 1)]
              for c in cacc],
             alinhar_dir={1, 2, 3, 4, 5}))
    a(f"""<p>O CAC blended do periodo e <strong>BRL {brl(cacb['cac_blended_brl'])}</strong>, considerando
todo o investimento de aquisicao de BRL {brl(cacb['spend_total_brl'])} sobre
{num(cacb['novos_clientes'],0)} clientes adquiridos. Se olhar apenas os canais com atribuicao, cai para
BRL {brl(cacb['cac_atribuivel_brl'])}, porque {pct(cacb['pct_spend_sem_atribuicao'])} do investimento esta
em Brand, que nao gera cliente rastreavel.</p>
<p><strong>Brand nao foi rateado entre os canais.</strong> Ratear melhoraria artificialmente o CAC de quem
converte e esconderia que 14% do orcamento de aquisicao nao tem medicao de retorno. O board deve olhar o
blended, porque Brand tambem foi pago.</p>""")
    a(f"""<div class="card"><p><strong>Product-Led e Partner sao os canais que sustentam a empresa</strong>,
com payback de {num(payb[0]['payback_meses'])} e {num(payb[1]['payback_meses'])} meses. Inbound e o pior,
com CAC de BRL {brl(next(c['cac_brl'] for c in cacc if c['canal']=='Inbound'))} e payback de
{num(next(x['payback_meses'] for x in payb if x['canal']=='Inbound'))} meses, quase quatro vezes o de
Product-Led para trazer metade dos clientes.</p></div>""")
    a("<h3>CAC por coorte trimestral</h3>")
    a('<div class="chart">' + viz.svg_linhas(
        [("CAC blended da coorte", [c["cac_blended_brl"] for c in coorte], viz.AMBAR)],
        [c["coorte"] for c in coorte]) + "</div>")
    a(tabela(["Coorte", "Investimento (BRL)", "Clientes", "CAC (BRL)"],
             [[c["coorte"], brl(c["spend_brl"]), num(c["novos_clientes"], 0), brl(c["cac_blended_brl"])]
              for c in coorte], alinhar_dir={1, 2, 3}))
    a(f"""<p>A eficiencia de aquisicao <strong>melhorou</strong>: de BRL {brl(coorte[0]['cac_blended_brl'])}
na coorte {coorte[0]['coorte']} para BRL {brl(coorte[-3]['cac_blended_brl'])} em {coorte[-3]['coorte']}. O
salto do ultimo trimestre nao deve ser lido como deterioracao: parte dos clientes atraidos pelo
investimento do trimestre ainda nao converteu na data de corte, e o denominador esta incompleto.</p>""")

    a("<h3>LTV e a razao LTV/CAC</h3>")
    a(f"""<div class="kpis">
<div class="kpi"><div class="rot">ARPA mensal</div><div class="val">{brl(ue['arpa_mensal_brl'])}</div></div>
<div class="kpi"><div class="rot">Contribuicao mensal</div><div class="val">{brl(ue['contribuicao_mensal_brl'])}</div>
<div class="obs">ARPA x margem bruta</div></div>
<div class="kpi"><div class="rot">LTV</div><div class="val">{brl(ue['ltv_brl'])}</div>
<div class="obs">com margem e churn de receita</div></div>
<div class="kpi"><div class="rot">Payback</div><div class="val">{num(ue['payback_meses'])} meses</div></div>
<div class="kpi"><div class="rot">LTV / CAC</div><div class="val">{num(ue['ltv_cac'], 1)}x</div></div>
</div>""")
    a(f"""<p>A formula usada e explicita: LTV = ARPA mensal x margem bruta / churn de receita mensal.
As duas escolhas importam. Usar receita bruta em vez de margem ignoraria que servir o cliente custa dinheiro;
usar churn de clientes em vez de churn de receita ignoraria que quem sai nao tem o ticket medio da base.
Pela formula ingenua, que troca as duas coisas, o LTV apareceria como
BRL {brl(ue['ltv_sem_margem_brl'])}, ou {pct(ue['ltv_sem_margem_brl']/ue['ltv_brl']-1)} acima.</p>""")
    a(f"""<div class="card alerta"><p><strong>Nao apresente {num(ue['ltv_cac'],1)}x como conquista.</strong>
A referencia de mercado saudavel e entre 3x e 5x. Um LTV/CAC de {num(ue['ltv_cac'],1)}x, com payback de
{num(ue['payback_meses'])} meses, quase nunca significa eficiencia excepcional: significa
<strong>subinvestimento em crescimento</strong> ou churn subestimado pela janela curta de historico.
A leitura gerencial correta e que existe espaco para acelerar aquisicao nos canais de payback baixo,
e nao que a empresa descobriu uma maquina de dinheiro.</p></div>""")

    # ---------------------------------------------------------- Pergunta 6
    a("<h2>Pergunta 6 &middot; Qualidade dos dados</h2>")
    a("<p class='sub'>O que foi encontrado de errado, ambiguo ou nao confiavel nas fontes, e para cada item o impacto no numero e a correcao pedida na origem.</p>")
    a("<p>A resposta tem duas camadas complementares. Primeiro o impacto quantificado dos defeitos sobre a receita, na forma de um encadeamento que sai do numero ingenuo e chega no numero correto (item 6.1). Depois a lista completa de defeitos por origem, com severidade e correcao pedida (item 6.2).</p>")
    a("<h3>6.1 &middot; O impacto dos defeitos sobre a receita: do numero ingenuo ao numero correto</h3>")
    a("""<p>Cada barra vermelha e um erro que inflava a receita, cada verde um erro que a reduzia. O
encadeamento sai do valor ingenuo e chega no valor auditado, e fecha no centavo por construcao: o pipeline
falha e nao publica se a soma dos ajustes nao reconstruir exatamente a diferenca.</p>""")
    a('<div class="chart">' + viz.svg_waterfall(
        [(b["efeito"].split(" ", 1)[-1] if b["efeito"].startswith("E") else b["efeito"],
          b["valor_brl"], b["papel"]) for b in bridge]) + "</div>")
    a(tabela(
        ["#", "Erro nao tratado", "Por que acontece", "Impacto (BRL)"],
        [[("<strong>=</strong>" if b["papel"] != "ajuste" else str(b["ordem"])),
          f"<strong>{esc(b['efeito'])}</strong>" if b["papel"] != "ajuste" else esc(b["efeito"]),
          esc(b["explicacao"]),
          f"<strong>{brl(b['valor_brl'])}</strong>" if b["papel"] != "ajuste" else brl(b["valor_brl"])]
         for b in bridge],
        alinhar_dir={3}, destaque=lambda n, l: bridge[n]["papel"] == "ajuste" and bridge[n]["valor_brl"] < 0))
    a(f"""<div class="card alerta"><p><strong>Leitura correta do quadro:</strong> a soma dos valores
absolutos dos ajustes e BRL {brl(erro_bruto)}, ou {pct(erro_bruto/bridge[-1]['valor_brl'])} da receita do
periodo. Esse e o tamanho real da exposicao do numero atual, e nao os
{pct(abs(erro_liq)/bridge[-1]['valor_brl'], 2)} da diferenca liquida.</p></div>""")

    a("<h4>Efeito sobre as outras metricas</h4>")
    a("""<p>Na receita os erros se cancelaram. Nas demais metricas nao houve essa sorte, porque cada uma
depende de um subconjunto diferente dos mesmos defeitos.</p>""")
    a(tabela(
        ["Metrica", "Sem tratamento", "Correto", "Erro", "Erro %"],
        [[esc(c["metrica"]),
          brl(c["valor_ingenuo"]) if c["unidade"] == "BRL" else num(c["valor_ingenuo"], 0),
          brl(c["valor_correto"]) if c["unidade"] == "BRL" else num(c["valor_correto"], 0),
          brl(c["valor_ingenuo"] - c["valor_correto"]) if c["unidade"] == "BRL"
              else num(c["valor_ingenuo"] - c["valor_correto"], 0),
          pct((c["valor_ingenuo"] - c["valor_correto"]) / abs(c["valor_correto"]), 1) if c["valor_correto"] else "n/d"]
         for c in comp],
        alinhar_dir={1, 2, 3, 4},
        destaque=lambda n, l: abs((comp[n]["valor_ingenuo"] - comp[n]["valor_correto"])
                                  / (comp[n]["valor_correto"] or 1)) > 0.25))
    a("""<div class="card"><p><strong>O MRR ingenuo erra 246%</strong> por um motivo unico e evitavel:
multiplicar por 12 o preco de assinaturas anuais. O enunciado das fontes e explicito em dizer que
<code>unit_price</code> ja e o preco mensal por assento nos dois ciclos de cobranca. Esse e o erro que mais
distorce a leitura de crescimento da empresa.</p>
<p><strong>O COGS ingenuo erra 91% para baixo</strong> por dois erros somados: o custo em dolar e somado como
se fosse real, e o <code>JOIN</code> com o mapa de workspace descarta silenciosamente os 27 workspaces sem
dono. O resultado e uma margem bruta aparente de 96%, contra os
{0} reais.</p></div>""".format(pct(um('SELECT 1 - sum(cogs_total_brl)/sum(receita_brl) FROM gold_margem_mensal'))))

    a("<h3>6.2 &middot; Cada defeito de origem, com severidade e correcao pedida</h3>")
    a("""<p>Cada item foi encontrado por verificacao automatica que continua rodando a cada execucao. A
coluna de impacto diz o que o defeito faz com o numero, nao apenas que ele existe.</p>""")
    achados = [
        ("Critico", "<code>faturas_export.csv</code> em cp1252 com preambulo de 5 linhas e rodape de totalizacao",
         "Leitura com utf-8 aborta a ingestao; skiprows fixo quebra se o preambulo mudar de tamanho e o rodape entra como registro fantasma.",
         "Exportar em utf-8, CSV puro, sem cabecalho humano nem linha de total."),
        ("Critico", "Tres formatos de data na mesma coluna (ISO, dd/mm/aaaa, dd-mm-aaaa)",
         "Parsing unico converte parte das datas em nulo e joga a receita para o mes errado ou para fora do periodo.",
         "Padronizar em ISO 8601 na origem e validar no momento da escrita."),
        ("Critico", "47 documentos duplicados, identicos exceto o formato da data",
         f"Inflaria a receita em BRL {brl(abs(next(b['valor_brl'] for b in bridge if b['ordem']==1)))}.",
         "Chave unica em numero_fatura no sistema de cobranca e export idempotente."),
        ("Critico", "35 notas de credito gravadas com valor positivo",
         f"Somar sem inverter o sinal desloca a receita em BRL {brl(abs(next(b['valor_brl'] for b in bridge if b['ordem']==3)))}.",
         "Gravar nota de credito com sinal negativo ou expor campo explicito de natureza do documento."),
        ("Critico", "27 workspaces sem cliente e 3 apontando para dois clientes diferentes",
         f"{pct(cogs_nao_atr_pct)} do custo de servir fica sem dono; a margem por cliente nao pode ser usada para decisao comercial.",
         "Tag de owner obrigatoria na criacao do workspace, com bloqueio de provisionamento sem ela."),
        ("Alto", "Custo de cloud em USD sem indicacao de conversao",
         f"Tratar como BRL subestima a receita e o custo; no periodo o efeito na receita foi de BRL {brl(next(b['valor_brl'] for b in bridge if b['ordem']==4))}.",
         "Carregar valor original, moeda e a taxa usada, nunca apenas o valor convertido."),
        ("Alto", "Plano com 13 grafias diferentes para 3 planos reais",
         "Qualquer agrupamento por plano se fragmenta e a margem por plano fica irreconhecivel.",
         "Enum fechado no produto, validado na escrita."),
        ("Alto", "Dois CNPJ com dois customer_id cada (Girassol Express, Duna Transportes)",
         "Conta a mesma empresa como dois clientes: infla aquisicao, distorce CAC e churn logico.",
         "Deduplicacao por CNPJ no cadastro e chave unica de entidade economica."),
        ("Alto", "3 assinaturas ativas com zero assentos",
         "Cobranca por assento com zero assento e impossivel; MRR do cliente fica zerado sem que ele tenha saido.",
         "Constraint de seats > 0 na criacao da assinatura."),
        ("Alto", "5 assinaturas com end_date anterior ao start_date",
         "Vigencia negativa remove o cliente da base de MRR em mes em que ele estava ativo.",
         "Validacao end_date >= start_date na escrita."),
        ("Medio", f"{um('SELECT count(*) FROM alerta_pagamentos_orfaos')} pagamentos sem fatura correspondente",
         f"BRL {brl(um('SELECT sum(valor_brl) FROM alerta_pagamentos_orfaos'))} de caixa que nao se atribui a cliente nem a competencia; quebra a reconciliacao com a contabilidade.",
         "Integridade referencial entre pagamento e documento fiscal."),
        ("Medio", "9 documentos onde valor_bruto menos desconto nao fecha com valor_liquido",
         "Indica calculo de desconto fora do sistema de cobranca; impede auditar a receita pela composicao do documento.",
         "Recalcular o liquido no sistema, nunca aceitar os tres campos como entrada independente."),
        ("Medio", "Dominio de canal divergente (PLG no cadastro, Product-Led no investimento)",
         "Sem harmonizacao o CAC de um canal fica infinito e do outro fica zero.",
         "Tabela unica de canais compartilhada entre Marketing e Produto."),
        ("Medio", "24 documentos cancelados e 1 cliente com signup em 2027",
         f"Cancelado somado como receita adiciona BRL {brl(abs(next(b['valor_brl'] for b in bridge if b['ordem']==2)))}; data futura cria coorte de aquisicao que nao existe.",
         "Filtro de status na definicao de receita e validacao de data contra a data de fechamento."),
        ("Imaterial", "4 assinaturas com billing_period nulo",
         "Impacto exatamente zero: unit_price e mensal nos dois ciclos, portanto o campo nao entra em nenhuma formula. Declarado para que a anomalia nao seja usada para desqualificar o resultado.",
         "Preencher por consistencia de cadastro, sem urgencia."),
    ]
    a(tabela(["Severidade", "Achado", "Impacto no numero", "Correcao pedida na origem"],
             [[f'<span class="tag {"err" if s in ("Critico","Alto") else ("ok" if s=="Imaterial" else "")}">{esc(s)}</span>',
               f"<strong>{ach}</strong>", imp, cor] for s, ach, imp, cor in achados]))

    # ---------------------------------------------------------- Pergunta 7
    a("<h2>Pergunta 7 &middot; Perenidade e linguagem comum</h2>")
    a("<p class='sub'>Como as definicoes deste documento continuam valendo daqui a um ano, com gente nova, fontes novas e alguem pedindo um numero as 18h. Mecanismo, nao intencao.</p>")
    a("""<p>A pergunta e o que impede tudo isto de virar mais uma planilha. A resposta nao pode ser
documentacao e alinhamento, porque nenhum dos dois resiste a uma sexta-feira de fechamento as 18h. O que
resiste e mecanismo: a definicao precisa estar em um lugar onde contraria-la quebra algo visivel.</p>""")
    a("""<div class="card"><h3 style="margin-top:0">Os cinco mecanismos, na ordem em que eu implantaria</h3>
<ol>
<li><strong>Definicao como codigo, nao como documento.</strong> As 15 premissas deste relatorio vivem em
<code>src/config.py</code> e sao lidas pelo pipeline e pelo relatorio da mesma fonte. Nao existe premissa
escrita em prosa que nao esteja vigente na execucao: mudar o texto sem mudar a regra e impossivel, porque o
texto <em>e</em> a regra. Ja implementado.</li>
<li><strong>Teste de reconciliacao que derruba a publicacao.</strong> Sao 26 verificacoes executadas em cada
rodada. As de severidade ERRO encerram o processo com codigo diferente de zero e nada e publicado: rateio
de competencia que nao devolve o valor do documento, decomposicao de MRR que nao fecha, nota de credito com
sinal positivo, preco fora da tabela do plano, documento com data posterior ao fechamento. Se alguem
alterar a regra de MRR sem pensar, a decomposicao deixa de fechar e o pipeline para. Ja implementado.</li>
<li><strong>Dono nomeado por definicao e nao por tabela.</strong> Receita reconhecida e receita diferida
pertencem a Contabilidade; MRR, churn e NRR pertencem a Vendas; COGS e alocacao de infraestrutura pertencem
a Infra. Dono e quem aprova mudanca, nao quem calcula. Sem nome proprio, a definicao volta a ser opiniao.</li>
<li><strong>Mudanca de definicao entra por pull request com registro de decisao.</strong> Alterar o que e
MRR exige um PR que muda a premissa em <code>config.py</code>, o teste correspondente e uma nota de decisao
com data, autor e motivo, aprovado pelo dono daquela definicao. O historico de por que a metrica mudou fica
no versionamento, e nao na memoria de quem estava na reuniao. O beneficio pratico e responder em segundos a
pergunta mais cara de um fechamento: o numero mudou porque o negocio mudou ou porque a regra mudou.</li>
<li><strong>Camada de consumo unica e sem atalho.</strong> Vendas, Contabilidade e Infra leem as tabelas
<code>gold_*</code>, nunca as fontes cruas. Numero que aparece em reuniao e nao existe na camada de consumo
nao e discutido, e virado em pedido de inclusao. E o que dissolve as tres planilhas paralelas, porque tira
o incentivo de cada area manter a sua.</li>
</ol></div>""")
    a("""<p>O que acontece as 18h de um dia de fechamento, concretamente: um comando
(<code>python run.py</code>) reconstroi tudo das fontes cruas as tabelas finais, roda as 26 verificacoes e
gera este relatorio. Se passar, o numero pode ser usado. Se nao passar, o log diz qual definicao foi
violada e por quanto, e a resposta correta a quem pediu o numero e que ele nao esta disponivel, com o
motivo. Um numero indisponivel com motivo e melhor do que um numero errado com confianca.</p>""")

    # ---------------------------------------------------------- Anexos
    a("<h2>Anexo A &middot; Premissas assumidas</h2>")
    a("""<p>O enunciado avisa que varias definicoes admitem mais de uma leitura e que a escolha faz parte da
avaliacao. Cada premissa abaixo traz a regra adotada, o motivo e a alternativa que foi rejeitada, porque
premissa sem alternativa declarada e apenas preferencia disfarcada de metodo.</p>""")
    a(tabela(["ID", "Tema", "Regra adotada", "Por que", "Alternativa rejeitada"],
             [[f"<strong>{k}</strong>", esc(v["tema"]), esc(v["regra"]), esc(v["porque"]),
               esc(v["alternativa"])] for k, v in sorted(PREMISSAS.items())]))

    a("<h2>Anexo B &middot; Resultado das verificacoes automaticas</h2>")
    blo = len(rel.falhas_bloqueantes)
    a(f"""<div class="card {'ok' if blo == 0 else 'critico'}"><p><strong>
{len(rel.itens)} verificacoes executadas, {blo} falhas bloqueantes, {len(rel.alertas)} alertas.</strong>
{'Os numeros deste relatorio passaram por todas as reconciliacoes obrigatorias.' if blo == 0 else 'Ha falha bloqueante: os numeros nao devem ser usados.'}
Os alertas nao invalidam o resultado, eles quantificam defeito de origem que ja esta refletido nas
premissas e na secao 8.</p></div>""")
    a(tabela(["Verificacao", "Severidade", "Resultado", "Detalhe"],
             [[f"<code>{esc(i.nome)}</code>", esc(i.severidade),
               '<span class="tag ok">passou</span>' if i.passou else
               f'<span class="tag err">{"falhou" if i.severidade == "ERRO" else "alerta"}</span>',
               esc(i.detalhe)] for i in rel.itens]))

    a("<h2>Anexo C &middot; Rastro de um numero, da fonte crua ao indicador</h2>")
    a("""<p>Duas amostras deliberadamente escolhidas, cada uma exercitando uma parte diferente do
pipeline. Juntas cobrem a resposta a "de onde vem esse numero" para os dois casos mais dificeis do
dataset: um contrato anual (rateio de competencia ao longo de 13 meses) e um documento em dolar
(conversao cambial pela PTAX do mes).</p>""")

    a("<h3>C.1 &middot; Contrato anual em BRL: rateio pro-rata mes a mes</h3>")
    anual = df("""
        SELECT r.numero_fatura, r.mes, r.moeda, r.competencia_inicio, r.competencia_fim,
               r.dias_competencia, r.dias_no_mes,
               r.valor_documento_moeda_origem, r.receita_moeda_origem, r.receita_brl
        FROM silver_receita_reconhecida r
        WHERE r.numero_fatura = (
            SELECT numero_fatura FROM silver_receita_reconhecida
            WHERE moeda='BRL' AND dias_competencia > 300
            GROUP BY 1 HAVING count(*) = 13
            ORDER BY max(valor_documento_moeda_origem) DESC LIMIT 1)
        ORDER BY r.mes""")
    if anual:
        nf = anual[0]["numero_fatura"]
        ini, fim = anual[0]["competencia_inicio"], anual[0]["competencia_fim"]
        valor_doc = anual[0]["valor_documento_moeda_origem"]
        dias_tot = anual[0]["dias_competencia"]
        soma_rat = sum(x["receita_brl"] for x in anual)
        a(f"""<p>Documento <code>{esc(nf)}</code>, contrato anual em BRL de <strong>BRL {brl(valor_doc, 2)}</strong>,
com competencia de {ini:%d/%m/%Y} a {fim:%d/%m/%Y} ({dias_tot} dias). Um relatorio ingenuo joga o valor
inteiro no mes de emissao. O pipeline abre em {len(anual)} parcelas mensais, cada uma proporcional aos dias
daquele mes que caem dentro da competencia.</p>""")
        a(tabela(["Mes de competencia", "Dias no mes", "Fracao do documento",
                  "Parcela reconhecida no mes (BRL)"],
                 [[x["mes"], num(x["dias_no_mes"], 0),
                   pct(x["dias_no_mes"] / x["dias_competencia"], 3),
                   brl(x["receita_brl"], 2)] for x in anual],
                 alinhar_dir={1, 2, 3}))
        a(f"""<div class="card ok"><p><strong>Prova de fechamento.</strong> A soma das {len(anual)} parcelas
e BRL {brl(soma_rat, 2)}, exatamente o valor original do documento (BRL {brl(valor_doc, 2)}).
Diferenca: BRL {brl(soma_rat - valor_doc, 4)}. Essa igualdade e uma das verificacoes bloqueantes do
Anexo B (<code>rateio_prorata_fecha</code>): se algum dia deixar de fechar por causa de refatoracao ou
mudanca de regra, o pipeline para antes de publicar.</p></div>""")
    else:
        a('<div class="card critico"><p>Sem contrato anual em BRL no dataset atual.</p></div>')

    a("<h3>C.2 &middot; Documento em USD: conversao pela PTAX do mes de competencia</h3>")
    usd = df("""
        SELECT r.numero_fatura, r.mes, r.competencia_inicio, r.competencia_fim, r.dias_competencia,
               r.valor_documento_moeda_origem, r.receita_moeda_origem,
               r.usd_brl_aplicado, fxm.usd_brl_min, fxm.usd_brl_max, r.receita_brl
        FROM silver_receita_reconhecida r
        LEFT JOIN silver_fx_mensal fxm ON fxm.mes = r.mes
        WHERE r.moeda='USD' AND r.dias_competencia BETWEEN 28 AND 31
        ORDER BY r.receita_brl DESC LIMIT 1""")
    if usd:
        u = usd[0]
        a(f"""<p>Documento <code>{esc(u['numero_fatura'])}</code>, mensal em USD, competencia de
{u['competencia_inicio']:%d/%m/%Y} a {u['competencia_fim']:%d/%m/%Y}. Valor original:
<strong>USD {num(u['valor_documento_moeda_origem'], 2)}</strong>. Um relatorio ingenuo somaria esse
valor a receita em BRL sem conversao, subestimando a receita do mes. O pipeline aplica a PTAX venda
media do mes de competencia (media aritmetica dos dias uteis publicados pelo Banco Central).</p>""")
        a(tabela(["Componente", "Valor"],
                 [["Documento (moeda de origem)", f"USD {num(u['valor_documento_moeda_origem'], 2)}"],
                  ["Dias da competencia", num(u["dias_competencia"], 0)],
                  ["Fracao reconhecida neste mes", pct(1.0)],
                  [f"PTAX venda media de {u['mes']}", num(u["usd_brl_aplicado"], 4)],
                  [f"Faixa da PTAX no mes {u['mes']}",
                   f"min {num(u['usd_brl_min'], 4)} &middot; max {num(u['usd_brl_max'], 4)}"],
                  ["Formula aplicada",
                   f"USD {num(u['valor_documento_moeda_origem'], 2)} &times; {num(u['usd_brl_aplicado'], 4)}"],
                  ["<strong>Receita reconhecida em BRL</strong>",
                   f"<strong>{brl(u['receita_brl'], 2)}</strong>"]],
                 alinhar_dir={1}))
        a(f"""<div class="card"><p>Esse e o caminho que sera percorrido na defesa: arquivo cru (linha do
CSV em cp1252, com o valor <code>{num(u['valor_documento_moeda_origem'], 2).replace('.', ',')}</code> e
moeda <code>USD</code>), deduplicacao pelo <code>numero_fatura</code>, parsing das datas de competencia
(no dataset ha tres formatos misturados), rateio diario da competencia, join com a serie mensal de PTAX
venda extraida da API do BCB, agregacao em <code>gold_receita_mensal</code>.</p></div>""")
    else:
        a('<div class="card critico"><p>Sem documento mensal em USD no dataset atual.</p></div>')

    fx_min, fx_max, fx_n = con.execute(
        "SELECT min(usd_brl), max(usd_brl), count(*) FROM silver_fx_diario").fetchone()
    a(f"""<footer>
<p><strong>Como reproduzir.</strong> <code>python run.py</code> reconstroi tudo do zero, de forma
idempotente; <code>python run.py --idempotencia</code> executa duas vezes e compara as tabelas de consumo.
Camadas: bronze (ingestao fiel, com linhagem por linha), silver (conformacao, deduplicacao e quarentena),
gold (indicadores). Engine local em DuckDB, transformacoes em SQL versionado, orquestracao em Python.</p>
<p><strong>Cambio.</strong> PTAX venda extraida da API de dados abertos do Banco Central, serie 1 do SGS:
{fx_n} cotacoes diarias no intervalo, entre {num(fx_min, 4)} e {num(fx_max, 4)}. Cotacao nao publicada em
fim de semana e feriado e resolvida por forward-fill do ultimo dia util, com marcacao de quais valores foram
preenchidos. O resultado fica em cache local para que o pipeline seja reproduzivel sem depender de rede.</p>
<p><strong>Escopo e limitacoes.</strong> Margem bruta cobre apenas custo de cloud; nao ha dados de suporte,
infraestrutura compartilhada de produto nem folha tecnica, portanto a margem real e menor que a reportada.
CAC usa investimento do mes de aquisicao, sem defasagem entre investimento e conversao. LTV assume churn
constante, premissa fragil em base com menos de 100 clientes. Nada deste projeto usa servico externo ou
plataforma de nuvem: todos os dados permanecem em arquivos locais.</p>
</footer>""")

    # ------------------------------------------------------------ arquivo
    doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="pipeline local Tellus (DuckDB + Python), sem dependencia externa">
<title>Tellus | Unit Economics</title>
<style>{CSS}</style>
</head>
<body>
{''.join(p)}
</body>
</html>"""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "relatorio_tellus.html"
    destino.write_text(doc, encoding="utf-8")
    log.info("relatorio escrito: %s (%.0f KB)", destino, len(doc) / 1024)
    return str(destino)
