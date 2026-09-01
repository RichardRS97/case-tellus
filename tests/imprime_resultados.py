import duckdb
con = duckdb.connect(r"C:\Users\vcp19001596\Desktop\Projetos\case_tellus_solucao\data\tellus_warehouse.duckdb", read_only=True)


def show(titulo, sql, fmt=None):
    print("\n" + "=" * 78)
    print(titulo)
    print("=" * 78)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    larg = [max(len(str(c)), 12) for c in cols]
    print(" | ".join(str(c).ljust(larg[i])[:22] for i, c in enumerate(cols)))
    for r in rows:
        out = []
        for i, v in enumerate(r):
            if isinstance(v, float):
                out.append(f"{v:,.2f}".rjust(larg[i])[:22])
            else:
                out.append(str(v).ljust(larg[i])[:22])
        print(" | ".join(out))


show("BRIDGE DE ERRO DA RECEITA (jan/24 a jun/26)",
     "SELECT ordem, efeito, round(valor_brl,2) AS valor_brl, papel FROM gold_bridge_receita ORDER BY ordem")

show("COMPARATIVO INGENUO x CORRETO",
     """SELECT ordem, metrica, unidade, round(valor_ingenuo,2) ingenuo, round(valor_correto,2) correto,
               round(valor_ingenuo - valor_correto,2) erro_abs,
               CASE WHEN valor_correto <> 0 THEN round(100.0*(valor_ingenuo-valor_correto)/abs(valor_correto),1) END erro_pct
        FROM gold_comparativo_metricas ORDER BY ordem""")

show("RECEITA x CAIXA (ultimos 12 meses da janela)",
     """SELECT mes, round(receita_reconhecida_brl,2) receita, round(caixa_liquido_brl,2) caixa,
               round(diferenca_brl,2) dif
        FROM gold_receita_vs_caixa ORDER BY mes DESC LIMIT 12""")

show("TOTAIS RECEITA x CAIXA DO PERIODO",
     """SELECT round(sum(receita_reconhecida_brl),2) receita_total,
               round(sum(caixa_liquido_brl),2) caixa_total,
               round(sum(caixa_liquido_brl)-sum(receita_reconhecida_brl),2) diferenca
        FROM gold_receita_vs_caixa""")

show("RECEITA DIFERIDA NO FECHAMENTO DE JUN/2026",
     "SELECT documentos_com_saldo, entidades, round(saldo_diferido_brl,2) saldo_brl, primeiro_mes, ultimo_mes FROM gold_receita_diferida_fechamento")

show("MRR / ARR ULTIMOS 12 MESES COM DECOMPOSICAO",
     """SELECT mes, round(mrr_brl,0) mrr, round(variacao_brl,0) var, round(novo_brl,0) novo,
               round(expansao_brl,0) expans, round(contracao_brl,0) contr, round(churn_brl,0) churn,
               round(efeito_cambio_brl,0) cambio, round(residuo_decomposicao_brl,4) residuo,
               clientes_ativos
        FROM gold_mrr_mensal WHERE mes >= '2025-07' ORDER BY mes""")

show("NRR 12 MESES",
     "SELECT * FROM gold_nrr_12m")

show("CHURN: TENDENCIA ANUAL",
     """SELECT ano, clientes_perdidos, round(mrr_perdido_brl,0) mrr_perdido,
               round(100*logo_churn_medio_mensal,2) logo_churn_mes_pct,
               round(100*revenue_churn_medio_mensal,2) rev_churn_mes_pct,
               round(100*revenue_churn_anualizado,1) rev_churn_ano_pct,
               round(100*nrr_medio_mensal,1) nrr_mes_pct
        FROM gold_churn_tendencia ORDER BY ano""")

show("MARGEM MENSAL (ultimos 12)",
     """SELECT mes, round(receita_brl,0) receita, round(cogs_atribuivel_brl,0) cogs_dir,
               round(cogs_nao_atribuivel_brl,0) cogs_nao_atr,
               round(100*margem_direta_pct,1) mg_direta_pct,
               round(100*margem_consolidada_pct,1) mg_consol_pct
        FROM gold_margem_mensal ORDER BY mes DESC LIMIT 12""")

show("MARGEM DO PERIODO CONSOLIDADA",
     """SELECT round(sum(receita_brl),0) receita, round(sum(cogs_atribuivel_brl),0) cogs_atribuivel,
               round(sum(cogs_nao_atribuivel_brl),0) cogs_nao_atribuivel,
               round(100*(1-sum(cogs_atribuivel_brl)/sum(receita_brl)),1) mg_direta_pct,
               round(100*(1-sum(cogs_total_brl)/sum(receita_brl)),1) mg_consolidada_pct
        FROM gold_margem_mensal""")

show("MARGEM POR PLANO", "SELECT plano, round(receita_brl,0) receita, round(cogs_atribuivel_brl,0) cogs, round(100*margem_direta_pct,1) mg_pct, entidades FROM gold_margem_por_plano ORDER BY receita DESC")

show("10 CLIENTES QUE MAIS DESTROEM VALOR",
     """SELECT entidade_id, nome_fantasia, plano_atual, round(receita_periodo_brl,0) receita,
               round(cogs_atribuivel_brl,0) cogs, round(margem_direta_brl,0) margem,
               round(100*margem_direta_pct,1) mg_pct
        FROM gold_margem_por_cliente WHERE NOT sem_custo_atribuido ORDER BY margem_direta_brl LIMIT 10""")

show("QUANTOS CLIENTES DESTROEM VALOR",
     """SELECT count(*) total, count(*) FILTER (WHERE destroi_valor) destroem,
               count(*) FILTER (WHERE sem_custo_atribuido) sem_custo,
               round(sum(margem_direta_brl) FILTER (WHERE destroi_valor),0) margem_negativa_brl
        FROM gold_margem_por_cliente""")

show("CAC POR CANAL", "SELECT canal, round(spend_brl,0) spend, novos_clientes, round(cac_brl,0) cac, sem_atribuicao FROM gold_cac_por_canal ORDER BY spend DESC")
show("CAC BLENDED", "SELECT round(spend_total_brl,0) spend_total, round(spend_sem_atribuicao_brl,0) spend_brand, round(100*pct_spend_sem_atribuicao,1) pct_brand, novos_clientes, round(cac_blended_brl,0) cac_blended, round(cac_atribuivel_brl,0) cac_atribuivel FROM gold_cac_blended")
show("CAC POR COORTE TRIMESTRAL", "SELECT * FROM gold_cac_por_coorte ORDER BY coorte")
show("UNIT ECONOMICS",
     """SELECT round(arpa_mensal_brl,0) arpa, round(100*gm_direta,1) gm_direta_pct, round(100*gm_consolidada,1) gm_consol_pct,
               round(100*revenue_churn_mensal,2) churn_rec_mes_pct, round(100*logo_churn_mensal,2) churn_logo_mes_pct,
               round(cac_blended_brl,0) cac, round(contribuicao_mensal_brl,0) contrib_mes,
               round(ltv_brl,0) ltv, round(ltv_sem_margem_brl,0) ltv_ingenuo,
               round(payback_meses,1) payback_meses, round(ltv_cac,2) ltv_cac
        FROM gold_unit_economics""")
show("PAYBACK POR CANAL", "SELECT canal, round(cac_brl,0) cac, novos_clientes, round(payback_meses,1) payback_meses, round(ltv_cac,2) ltv_cac FROM gold_payback_por_canal ORDER BY payback_meses")
show("COGS NAO ATRIBUIVEL POR MOTIVO",
     """SELECT motivo, count(DISTINCT workspace_id) workspaces, round(sum(custo_usd),0) usd, round(sum(custo_brl),0) brl
        FROM silver_cogs_nao_atribuivel GROUP BY 1 ORDER BY brl DESC""")
show("PLANOS: GRAFIAS NORMALIZADAS", "SELECT plano, count(DISTINCT plano_bruto) grafias, count(*) assinaturas FROM silver_assinaturas GROUP BY 1")
