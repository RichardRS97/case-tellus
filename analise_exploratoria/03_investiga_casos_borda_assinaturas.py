import json
from collections import defaultdict

BASE = r"C:\Users\vcp19001596\Desktop\Projetos\dados_case_tellus"
subs = [json.loads(l) for l in open(f"{BASE}/assinaturas.jsonl", encoding="utf-8") if l.strip()]

print("=== subscription_id duplicados: as duas linhas sao identicas? ===")
by = defaultdict(list)
for s in subs:
    by[s["subscription_id"]].append(s)
for k, v in by.items():
    if len(v) > 1:
        iguais = all(v[0] == x for x in v[1:])
        print(f"\n{k}  identicas={iguais}")
        for x in v:
            print("   ", {kk: x[kk] for kk in ("customer_id", "plan", "seats", "unit_price", "currency", "billing_period", "start_date", "end_date", "status")})

print("\n=== end_date < start_date ===")
for s in subs:
    if s.get("end_date") and s["end_date"] < s["start_date"]:
        print("   ", {kk: s[kk] for kk in ("subscription_id", "customer_id", "plan", "seats", "start_date", "end_date", "canceled_at", "status")})

print("\n=== seats nulo/zero/texto ===")
for s in subs:
    if not s.get("seats") or str(s.get("seats")).strip() in ("0", "None", ""):
        print("   ", {kk: s[kk] for kk in ("subscription_id", "customer_id", "plan", "seats", "unit_price", "start_date", "end_date", "status")})

print("\n=== billing_period nulo ===")
for s in subs:
    if not s.get("billing_period"):
        print("   ", {kk: s[kk] for kk in ("subscription_id", "customer_id", "plan", "seats", "unit_price", "currency", "billing_period", "start_date", "status")})

print("\n=== sobreposicao de vigencia no mesmo cliente ===")
for c, lst in by_c.items() if (by_c := defaultdict(list)) is None else []:
    pass
by_c = defaultdict(list)
for s in subs:
    by_c[s["customer_id"]].append(s)
for c, lst in by_c.items():
    lst = sorted(lst, key=lambda x: x["start_date"])
    for i in range(len(lst) - 1):
        fim = lst[i].get("end_date")
        if fim and lst[i + 1]["start_date"] < fim:
            print(f"   {c}: {lst[i]['subscription_id']} [{lst[i]['start_date']}..{fim}] status={lst[i]['status']}"
                  f"  SOBREPOE  {lst[i+1]['subscription_id']} [{lst[i+1]['start_date']}..{lst[i+1].get('end_date')}]")

print("\n=== consistencia: unit_price fora do preco de tabela do plano/moeda ===")
tab = {("Starter", "BRL"): 89.0, ("Growth", "BRL"): 189.0, ("Enterprise", "BRL"): 349.0,
       ("Starter", "USD"): 19.0, ("Growth", "USD"): 39.0, ("Enterprise", "USD"): 69.0}
norm = {"starter": "Starter", "growth": "Growth", "enterprise": "Enterprise", "ent": "Enterprise"}
fora = 0
for s in subs:
    p = norm[str(s["plan"]).strip().lower()]
    up = s["unit_price"]
    up = float(str(up).replace(",", ".")) if isinstance(up, str) else float(up)
    esp = tab.get((p, s["currency"]))
    if esp is None or abs(up - esp) > 0.01:
        fora += 1
        if fora <= 8:
            print(f"   {s['subscription_id']} plano={p} moeda={s['currency']} unit_price={up} esperado={esp}")
print("   total fora de tabela:", fora)
