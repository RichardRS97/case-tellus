"""Investigacao 1: workspaces sem mapeamento para cliente.
Hipotese a testar: sao infra compartilhada (plataforma) ou falha de cadastro.
Investigacao 2: API do BCB SGS serie 1 (dolar comercial venda).
"""
import csv
import json
import sqlite3
import urllib.request
from collections import Counter, defaultdict

BASE = r"C:\Users\vcp19001596\Desktop\Projetos\dados_case_tellus"

infra = list(csv.DictReader(open(f"{BASE}/infra_costs.csv", encoding="utf-8")))
wmap = {r["workspace_id"]: r["customer_id"] for r in csv.DictReader(open(f"{BASE}/workspace_map.csv", encoding="utf-8"))}

print("=" * 72)
print("A. WORKSPACES ORFAOS")
print("=" * 72)
orf = sorted({r["workspace_id"] for r in infra} - set(wmap))
tot = defaultdict(float)
svc = defaultdict(lambda: defaultdict(float))
meses = defaultdict(set)
for r in infra:
    ws = r["workspace_id"]
    tot[ws] += float(r["cost_usd"])
    svc[ws][r["service"]] += float(r["cost_usd"])
    meses[ws].add(r["month"])

print(f"{'workspace':12} {'orfao':6} {'USD total':>12} {'meses':>6}  mix de servico")
for ws in sorted(tot, key=lambda x: -tot[x])[:20]:
    mix = ", ".join(f"{k}={svc[ws][k]/tot[ws]*100:.0f}%" for k in sorted(svc[ws], key=lambda k: -svc[ws][k]))
    print(f"{ws:12} {'SIM' if ws in orf else '-':6} {tot[ws]:12.2f} {len(meses[ws]):6}  {mix}")

print("\ncusto medio por workspace:")
o = [tot[w] for w in orf]
m = [tot[w] for w in tot if w not in orf]
print(f"  orfaos  : n={len(o):3} soma={sum(o):12.2f} media={sum(o)/len(o):10.2f}")
print(f"  mapeados: n={len(m):3} soma={sum(m):12.2f} media={sum(m)/len(m):10.2f}")
print(f"  razao de custo medio orfao/mapeado: {(sum(o)/len(o))/(sum(m)/len(m)):.2f}x")

print("\nnumeracao dos orfaos vs mapeados (ha padrao de faixa?):")
print("  orfaos :", orf)
print("  mapeados (primeiros 15):", sorted(wmap)[:15])
print("  ws no map sem custo:", sorted(set(wmap) - {r['workspace_id'] for r in infra}))

print("\nmix de servico agregado:")
for grupo, lst in (("ORFAOS", orf), ("MAPEADOS", [w for w in tot if w not in orf])):
    agg = defaultdict(float)
    for w in lst:
        for s, v in svc[w].items():
            agg[s] += v
    t = sum(agg.values())
    print(f"  {grupo:9}", ", ".join(f"{k}={agg[k]/t*100:.1f}%" for k in sorted(agg, key=lambda k: -agg[k])))

# quantos meses cada grupo aparece
print("\ncobertura temporal: orfaos aparecem em todos os 30 meses?")
print("  meses distintos por orfao:", Counter(len(meses[w]) for w in orf))
print("  meses distintos por mapeado:", Counter(len(meses[w]) for w in tot if w not in orf))

# negativos e duplicatas
neg = [r for r in infra if float(r["cost_usd"]) < 0]
print("\nregistros com custo negativo (credito de cloud):")
for r in neg:
    print("   ", r)
g = Counter((r["month"], r["workspace_id"], r["service"]) for r in infra)
print("\nchaves duplicadas (month,ws,service):")
for k, v in g.items():
    if v > 1:
        print("   ", k, "x", v, "->", [r["cost_usd"] for r in infra if (r["month"], r["workspace_id"], r["service"]) == k])

# =========================================================== BCB
print("\n" + "=" * 72)
print("B. API BCB SGS SERIE 1 (dolar comercial venda)")
print("=" * 72)
urls = [
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial=01/01/2024&dataFinal=31/01/2024",
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/5?formato=json",
]
for u in urls:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "tellus-case/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"OK  {u}")
        print("    registros:", len(data), "| amostra:", data[:3])
    except Exception as e:
        print(f"ERRO {u}\n     {type(e).__name__}: {e}")
