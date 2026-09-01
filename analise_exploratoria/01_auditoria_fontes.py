"""Auditoria exploratoria das fontes do case Tellus.
Roda antes de qualquer transformacao: mapeia armadilhas, anomalias e quebras
de integridade referencial. Nao escreve nada, apenas reporta.
"""
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date

BASE = r"C:\Users\vcp19001596\Desktop\Projetos\dados_case_tellus"


def sec(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def read_text(path):
    b = open(path, "rb").read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            txt = b.decode(enc)
            print(f"[encoding] {path.rsplit(chr(92), 1)[-1]} -> {enc}")
            return txt
        except UnicodeDecodeError:
            continue
    raise RuntimeError("encoding desconhecido: " + path)


def num(s):
    """Converte string monetaria pt-BR ou en-US para float."""
    s = (s or "").strip()
    if not s:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if "," in s and "." in s:          # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                      # 1234,56
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(d):
    """Retorna (date|None, rotulo_do_formato)."""
    d = (d or "").strip()
    if not d:
        return None, "vazio"
    for rx, fmt, lbl in (
        (r"^\d{4}-\d{2}-\d{2}$", (0, 1, 2), "ISO yyyy-mm-dd"),
        (r"^\d{2}/\d{2}/\d{4}$", (2, 1, 0), "BR dd/mm/yyyy"),
        (r"^\d{2}-\d{2}-\d{4}$", (2, 1, 0), "BR-dash dd-mm-yyyy"),
    ):
        if re.match(rx, d):
            p = re.split(r"[-/]", d)
            y, m, dd = p[fmt[0]], p[fmt[1]], p[fmt[2]]
            try:
                return date(int(y), int(m), int(dd)), lbl
            except ValueError:
                return None, "data invalida: " + d
    return None, "nao reconhecido: " + d


# =============================================================== FATURAS
sec("1. FATURAS_EXPORT.CSV")
raw = read_text(f"{BASE}/faturas_export.csv").splitlines()
print("preambulo:")
for l in raw[:5]:
    print("   |", l[:100])
hdr = next(i for i, l in enumerate(raw) if l.startswith("numero_fatura"))
print(f"header na linha {hdr} (as {hdr} primeiras devem ser descartadas), separador ';'")
rows = list(csv.DictReader(raw[hdr:], delimiter=";"))
print("registros:", len(rows))

malformadas = [r for r in rows if r.get("numero_fatura") is None or r.get("tipo") is None]
print("\nlinhas malformadas / campos None:", len(malformadas))
for r in malformadas:
    print("   ", r)

ok = [r for r in rows if r not in malformadas]
print("\ntipo:", Counter(r["tipo"] for r in ok))
print("status:", Counter(r["status"] for r in ok))
print("moeda:", Counter(r["moeda"] for r in ok))

for col in ("data_emissao", "competencia_inicio", "competencia_fim"):
    c = Counter(parse_date(r[col])[1] for r in ok)
    print(f"formatos {col}:", dict(c))

# duplicidade de numero de fatura
cnt = Counter(r["numero_fatura"] for r in ok)
dups = {k: v for k, v in cnt.items() if v > 1}
print("\nnumero_fatura duplicado:", len(dups), "| linhas extra:", sum(v - 1 for v in dups.values()))
print("as duplicatas sao identicas em valor? (checando bruto/liquido/moeda/cliente)")
identicas = 0
for k in dups:
    g = [r for r in ok if r["numero_fatura"] == k]
    chave = {(r["id_cliente"], r["valor_liquido"], r["moeda"], r["tipo"]) for r in g}
    if len(chave) == 1:
        identicas += 1
print(f"   duplicatas com mesmo cliente/valor/moeda/tipo: {identicas} de {len(dups)}")
print("   => duplicata logica com data em formato diferente (mesmo doc reexportado)")
ex = list(dups)[0]
for r in [r for r in ok if r["numero_fatura"] == ex]:
    print("   ex:", r["numero_fatura"], r["data_emissao"], r["competencia_inicio"], r["valor_liquido"], r["moeda"])

# notas de credito e sinais
cred = [r for r in ok if r["tipo"] != "FATURA"]
print("\nNOTA_CREDITO:", len(cred))
sinais = Counter("negativo" if (num(r["valor_liquido"]) or 0) < 0 else "positivo" for r in cred)
print("   sinal do valor_liquido nas notas de credito:", dict(sinais))
print("   ARMADILHA: se positivo, somar tudo infla a receita; precisa inverter sinal")
for r in cred[:5]:
    print("   ex:", r["numero_fatura"], r["tipo"], r["valor_bruto"], r["valor_liquido"], r["moeda"], r["status"])

print("\nvalores negativos em faturas normais:", sum(1 for r in ok if r["tipo"] == "FATURA" and (num(r["valor_liquido"]) or 0) < 0))

bad = sum(1 for r in ok if None not in (num(r["valor_bruto"]), num(r["desconto"]), num(r["valor_liquido"]))
          and abs((num(r["valor_bruto"]) - num(r["desconto"])) - num(r["valor_liquido"])) > 0.01)
print("linhas onde bruto - desconto != liquido:", bad)

# competencia multi-mes (anual)
multi = []
for r in ok:
    a, _ = parse_date(r["competencia_inicio"])
    b, _ = parse_date(r["competencia_fim"])
    if a and b:
        meses = (b.year - a.year) * 12 + (b.month - a.month) + 1
        if meses > 2:
            multi.append((r["numero_fatura"], r["competencia_inicio"], r["competencia_fim"], meses, r["valor_liquido"], r["moeda"]))
print("\nfaturas cobrindo >2 meses de competencia (contratos anuais):", len(multi))
for m in multi[:6]:
    print("   ", m)
print("   ARMADILHA: reconhecer o valor integral no mes da emissao infla receita e cria receita diferida errada")

# emissao fora do periodo / posterior ao corte
CUT = date(2026, 7, 15)
fut = [r["numero_fatura"] for r in ok if (parse_date(r["data_emissao"])[0] or date(2000, 1, 1)) > CUT]
print("faturas emitidas depois da data de corte 15/07/2026:", len(fut), fut[:5])
emis = [parse_date(r["data_emissao"])[0] for r in ok if parse_date(r["data_emissao"])[0]]
print("data_emissao min/max:", min(emis), max(emis))
comp = [parse_date(r["competencia_inicio"])[0] for r in ok if parse_date(r["competencia_inicio"])[0]]
print("competencia_inicio min/max:", min(comp), max(comp))
print("   nota: periodo de analise pedido = 2024-01 a 2026-06; ha competencia anterior a 2024")

# =============================================================== ASSINATURAS
sec("2. ASSINATURAS.JSONL")
subs = [json.loads(l) for l in read_text(f"{BASE}/assinaturas.jsonl").splitlines() if l.strip()]
print("registros:", len(subs))
print("plan (cru):", dict(Counter(s.get("plan") for s in subs)))
print("   ARMADILHA: mesmo plano com caixa diferente (starter/Starter/STARTER) -> group by quebra")
print("status:", dict(Counter(s.get("status") for s in subs)))
print("billing_period:", dict(Counter(s.get("billing_period") for s in subs)))
print("currency:", dict(Counter(s.get("currency") for s in subs)))
print("tipo de seats:", dict(Counter(type(s.get("seats")).__name__ for s in subs)))
print("   ARMADILHA: seats como texto -> soma vira concatenacao ou erro")
print("tipo de unit_price:", dict(Counter(type(s.get("unit_price")).__name__ for s in subs)))

print("\nunit_price por plano normalizado:")
pp = defaultdict(Counter)
for s in subs:
    pp[str(s.get("plan")).strip().lower()][s.get("unit_price")] += 1
for k in sorted(pp):
    print("   ", k, dict(pp[k]))

print("\nsubscription_id duplicado:", {k: v for k, v in Counter(s["subscription_id"] for s in subs).items() if v > 1})
print("seats nulo/zero:", sum(1 for s in subs if not s.get("seats") or str(s.get("seats")).strip() in ("0", "None", "")))
print("unit_price nulo:", sum(1 for s in subs if s.get("unit_price") in (None, 0)))
print("status=canceled sem canceled_at:", sum(1 for s in subs if s.get("status") == "canceled" and not s.get("canceled_at")))
print("canceled_at preenchido com status != canceled:", sum(1 for s in subs if s.get("canceled_at") and s.get("status") != "canceled"))
print("end_date < start_date:", sum(1 for s in subs if s.get("end_date") and s["end_date"] < s["start_date"]))
print("status=active com end_date preenchido:", sum(1 for s in subs if s.get("status") == "active" and s.get("end_date")))
print("status!=active sem end_date:", sum(1 for s in subs if s.get("status") != "active" and not s.get("end_date")))

# sobreposicao de assinaturas do mesmo cliente
bycust = defaultdict(list)
for s in subs:
    bycust[s["customer_id"]].append(s)
overlap = 0
for c, lst in bycust.items():
    lst2 = sorted(lst, key=lambda x: x["start_date"])
    for i in range(len(lst2) - 1):
        fim = lst2[i].get("end_date")
        if fim and lst2[i + 1]["start_date"] < fim:
            overlap += 1
print("pares de assinaturas do mesmo cliente com sobreposicao de periodo:", overlap)
print("   ARMADILHA: se ha sobreposicao, contar MRR de todas duplica receita do cliente")
print("clientes com mais de 1 assinatura:", sum(1 for v in bycust.values() if len(v) > 1))
print("assinaturas em USD:", sum(1 for s in subs if s.get("currency") == "USD"))

# =============================================================== INFRA
sec("3. INFRA_COSTS.CSV + WORKSPACE_MAP.CSV")
infra = list(csv.DictReader(read_text(f"{BASE}/infra_costs.csv").splitlines()))
print("registros:", len(infra))
print("service:", dict(Counter(r["service"] for r in infra)))
print("month min/max:", min(r["month"] for r in infra), max(r["month"] for r in infra))
vals = [num(r["cost_usd"]) for r in infra]
print("cost_usd nulo/ilegivel:", sum(1 for v in vals if v is None))
vv = [v for v in vals if v is not None]
print("negativos:", sum(1 for v in vv if v < 0), "| zero:", sum(1 for v in vv if v == 0))
print("soma USD:", round(sum(vv), 2), "| max:", max(vv), "| p99 aprox:", sorted(vv)[int(len(vv) * .99)])
print("top 5:", sorted(vv, reverse=True)[:5])
print("   nota: custo em USD, reporte em BRL -> exige cambio por mes de competencia")
g = Counter((r["month"], r["workspace_id"], r["service"]) for r in infra)
print("granularidade duplicada (month,ws,service):", sum(1 for v in g.values() if v > 1))
print("meses distintos:", len({r["month"] for r in infra}), "| workspaces distintos:", len({r["workspace_id"] for r in infra}))

wmap = list(csv.DictReader(read_text(f"{BASE}/workspace_map.csv").splitlines()))
print("\nworkspace_map registros:", len(wmap))
seen = Counter(r["workspace_id"] for r in wmap)
print("workspace_id duplicado no map:", sum(1 for v in seen.values() if v > 1))
percust = Counter(r["customer_id"] for r in wmap)
print("clientes com >1 workspace:", sum(1 for v in percust.values() if v > 1), "| max ws/cliente:", max(percust.values()))
print("   ARMADILHA: join ws->cliente e N:1, agregar sem cuidado duplica custo")
ws_infra = {r["workspace_id"] for r in infra}
ws_map = {r["workspace_id"] for r in wmap}
orf = sorted(ws_infra - ws_map)
print("workspaces com custo mas SEM cliente mapeado:", len(orf), orf[:10])
custo_orf = sum(num(r["cost_usd"]) or 0 for r in infra if r["workspace_id"] in (ws_infra - ws_map))
print("   custo USD nao alocavel:", round(custo_orf, 2), f"({round(100*custo_orf/sum(vv),2)}% do total)")
print("workspaces mapeados sem custo:", len(ws_map - ws_infra))

# =============================================================== SQLITE
sec("4. SQLITE tellus_financeiro.db")
con = sqlite3.connect(f"{BASE}/tellus_financeiro.db")
cur = con.cursor()
q = lambda s: cur.execute(s).fetchall()

print("customers:", q("select count(*) from customers")[0][0])
print("  country:", q("select country,count(*) from customers group by 1"))
print("  segment:", q("select segment,count(*) from customers group by 1"))
print("  channel:", q("select acquisition_channel,count(*) from customers group by 1"))
print("  signup min/max:", q("select min(signup_date),max(signup_date) from customers")[0])
print("  customer_id duplicado:", q("select count(*) from (select customer_id from customers group by 1 having count(*)>1)")[0][0])
print("  tax_id duplicado (mesmo CNPJ, ids diferentes):", q("select count(*) from (select tax_id from customers group by 1 having count(*)>1)")[0][0])
for r in q("select tax_id,group_concat(customer_id),group_concat(trade_name) from customers group by 1 having count(*)>1 limit 5"):
    print("     ", r)

print("\npayments:", q("select count(*) from payments")[0][0])
print("  currency:", q("select currency,count(*) from payments group by 1"))
print("  method:", q("select method,count(*) from payments group by 1"))
print("  paid_at min/max:", q("select min(paid_at),max(paid_at) from payments")[0])
print("  tamanhos de paid_at:", q("select length(paid_at),count(*) from payments group by 1"))
print("  amount min/max/avg/sum:", [round(x, 2) if x else x for x in q("select min(amount),max(amount),avg(amount),sum(amount) from payments")[0]])
print("  amount nulo:", q("select count(*) from payments where amount is null")[0][0])
print("  amount negativo:", q("select count(*) from payments where amount<0")[0][0])
print("  payment_id duplicado:", q("select count(*) from (select payment_id from payments group by 1 having count(*)>1)")[0][0])
print("  faturas com >1 pagamento:", q("select count(*) from (select numero_fatura from payments group by 1 having count(*)>1)")[0][0])

inv_ids = {r["numero_fatura"] for r in ok}
pay_inv = [r[0] for r in q("select numero_fatura from payments")]
print("  pagamentos sem fatura correspondente (orfaos):", len(set(pay_inv) - inv_ids))
print("  faturas sem nenhum pagamento:", len(inv_ids - set(pay_inv)))

print("\nsales_marketing_spend:", q("select count(*) from sales_marketing_spend")[0][0])
print("  month min/max:", q("select min(month),max(month) from sales_marketing_spend")[0])
print("  por canal:", [(c, n, round(s, 2)) for c, n, s in q("select channel,count(*),sum(spend_brl) from sales_marketing_spend group by 1")])
print("  spend nulo/negativo:", q("select count(*) from sales_marketing_spend where spend_brl is null or spend_brl<0")[0][0])
print("  ATENCAO: canais em spend vs acquisition_channel em customers:")
print("    spend:", sorted({r[0] for r in q("select distinct channel from sales_marketing_spend")}))
print("    customers:", sorted({r[0] for r in q("select distinct acquisition_channel from customers")}))

sec("5. INTEGRIDADE REFERENCIAL CRUZADA")
db_cust = {r[0] for r in q("select customer_id from customers")}
inv_cust = {r["id_cliente"] for r in ok}
sub_cust = {s["customer_id"] for s in subs}
map_cust = {r["customer_id"] for r in wmap}
print("clientes: customers=", len(db_cust), "faturas=", len(inv_cust), "assinaturas=", len(sub_cust), "workspace_map=", len(map_cust))
print("em faturas e nao em customers:", sorted(inv_cust - db_cust))
print("em assinaturas e nao em customers:", sorted(sub_cust - db_cust))
print("em workspace_map e nao em customers:", sorted(map_cust - db_cust))
print("em customers sem assinatura:", sorted(db_cust - sub_cust))
print("em customers sem workspace:", len(db_cust - map_cust), sorted(db_cust - map_cust)[:10])
sub_ids = {s["subscription_id"] for s in subs}
print("id_assinatura em faturas inexistente em assinaturas:", len({r["id_assinatura"] for r in ok} - sub_ids))

print("\nfatura cujo id_cliente difere do customer_id da assinatura:")
sub2cust = {s["subscription_id"]: s["customer_id"] for s in subs}
mism = [(r["numero_fatura"], r["id_cliente"], sub2cust.get(r["id_assinatura"])) for r in ok
        if r["id_assinatura"] in sub2cust and sub2cust[r["id_assinatura"]] != r["id_cliente"]]
print("   ", len(mism), mism[:5])

sec("6. CONFRONTO FATURA x PAGAMENTO (unidade/moeda)")
inv_val = {r["numero_fatura"]: (num(r["valor_liquido"]), r["moeda"]) for r in ok}
rat = []
for nf, amt, cu in q("select numero_fatura,amount,currency from payments"):
    if nf in inv_val and inv_val[nf][0]:
        v, m = inv_val[nf]
        rat.append((nf, v, m, amt, cu, amt / v))
print("pares comparaveis:", len(rat))
print("amostra:")
for r in rat[:10]:
    print("   fat=%s %.2f %s | pgto=%.2f %s | razao=%.3f" % r)
print("distribuicao arredondada das razoes:", Counter(round(r[5], 1) for r in rat).most_common(12))
print("razao media:", round(sum(r[5] for r in rat) / len(rat), 3))
usd = [r for r in rat if r[2] == "USD"]
brl = [r for r in rat if r[2] == "BRL"]
print("razao media quando fatura em USD:", round(sum(r[5] for r in usd) / len(usd), 3), f"(n={len(usd)})")
print("razao media quando fatura em BRL:", round(sum(r[5] for r in brl) / len(brl), 3), f"(n={len(brl)})")
print("   nota: se razao ~1 em BRL e ~5-6 em USD, pagamento esta convertido para BRL")
