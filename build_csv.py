# -*- coding: utf-8 -*-
"""从最新快照 JSON 重建 CSV，供 snapshot_live.py 使用"""
import json, csv, io

with open(r"C:\Users\Administrator\WorkBuddy\2026-07-27-11-53-42\portfolio_snapshots\2026-07-30.json", "r", encoding="utf-8") as f:
    snap = json.load(f)

holdings = snap["holdings"]
summary = snap["summary"]

# Build CSV rows (14 columns)
rows = []

# Exchange rates header
rows.append(["","US > RMB, 6.78","","","","","","","","","","","",""])
rows.append(["","HK > RMB, 0.86","","","","","","","","","","","",""])
rows.append(["2026/07/30","","","","","","","","","","","","",""])

# Header
rows.append(["","","公司名称","代码","成本价","现价","涨跌幅","占比","仓位","数量","投入","当前","收益","股息"])

# Position data
for i, h in enumerate(holdings):
    market_map = {"CN": "A股", "HK": "港股", "US": "美股"}
    market_label = h["market"]
    cost = h.get("cost_price_raw") or ""
    qty = h.get("quantity") or 0
    invested = h.get("invested") or 0
    dividends = h.get("dividends") or ""
    code = h.get("code") or ""
    name = h.get("name") or ""

    rows.append([
        str(i+1),
        market_label,
        name,
        code,
        cost,
        "",  # 现价
        "",  # 涨跌幅
        "",  # 占比
        "",  # 仓位
        str(qty) if qty else "",
        str(invested),
        "",  # 当前
        "",  # 收益
        str(dividends) if dividends else "",
    ])

# Total row
total_inv = sum(h.get("invested", 0) or 0 for h in holdings)
total_cur = sum(h.get("current", 0) or 0 for h in holdings)
total_pnl = round(total_cur - total_inv, 2)
rows.append(["","总计","","","","","","","","",str(total_inv), str(total_cur), str(total_pnl), ""])

# Summary area
regions = summary.get("regions", {})
rows.append(["","","","","","","","整体","","", str(regions.get("整体",{}).get("invested","")), str(regions.get("整体",{}).get("current","")), str(regions.get("整体",{}).get("pnl","")), ""])
rows.append(["","","","","","","","国内","","", str(regions.get("国内",{}).get("invested","")), str(regions.get("国内",{}).get("current","")), str(regions.get("国内",{}).get("pnl","")), ""])
rows.append(["","","","","","","","境外","","", str(regions.get("境外",{}).get("invested","")), str(regions.get("境外",{}).get("current","")), str(regions.get("境外",{}).get("pnl","")), ""])

output = io.StringIO()
writer = csv.writer(output)
for row in rows:
    writer.writerow(row)

csv_content = output.getvalue()

with open(r"C:\Users\Administrator\WorkBuddy\2026-07-27-11-53-42\.tmp_csv.csv", "w", encoding="utf-8", newline="") as f:
    f.write(csv_content)

print("CSV generated successfully")
print(f"Positions: {len([h for h in holdings if h.get('code')])} stocks, {len(holdings)} total holdings")
print(f"Total invested: {total_inv}, Total current: {total_cur}")

# Print codes for next step
codes = []
for h in holdings:
    code = h.get("code")
    if code:
        codes.append(code)
print("CODES:", ",".join(codes))
