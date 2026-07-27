# Let me check what the user's actual position rate data looks like
import json
s = json.load(open("C:/Users/Administrator/WorkBuddy/2026-07-27-11-53-42/portfolio_snapshots/2026-07-27.json", encoding="utf-8"))
print("=== SUMMARY ===")
for k, v in s["summary"].items():
    if isinstance(v, dict):
        print(f"  {k}:")
        for rk, rv in v.items():
            print(f"    {rk}: {rv}")
    elif v is not None:
        print(f"  {k}: {v}")
print("\n=== REGIONS (invested/base vs current/base) ===")
base = s["summary"]["base"]
regions = s["summary"]["regions"]
for r in ["整体", "国内", "境外"]:
    inv = regions[r]["invested"]
    cur = regions[r]["current"]
    print(f"  {r}: invested/base={inv/base*100:.2f}%  current/base={cur/base*100:.2f}%")

print("\n=== HOLDINGS pos_curr_pct ===")
for h in s["holdings"]:
    print(f"  {h['name']}: pos_curr={h.get('pos_curr_pct')}%")
