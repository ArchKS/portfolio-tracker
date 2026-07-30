# -*- coding: utf-8 -*-
"""
持仓快照生成器 — 基于外部行情 API
用法：
  python snapshot_live.py <csv_file> <prices_json>
csv_file: 腾讯文档导出的持仓表
prices_json: {"code": price, ...} 来自 westock-mcp data_quote
"""
import csv, json, sys, os, re
from datetime import datetime, timezone, timedelta

def parse_amount(val):
    if not val or not val.strip(): return None
    s = val.strip().replace("¥","").replace("HK$","").replace("$","").replace(",","")
    m = 1.0
    if "万" in s: s = s.replace("万","").strip(); m = 10000
    elif "亿" in s: s = s.replace("亿","").strip(); m = 1e8
    try: return round(float(s) * m, 2)
    except: return None

def parse_percent(val):
    if not val or not val.strip(): return None
    try: return round(float(val.strip().replace("%","").replace(",","")), 4)
    except: return None

def parse_qty(val):
    if not val or not val.strip(): return None
    try: return int(float(val.strip().replace(",","")))
    except: return None

def parse_holdings(csv_text):
    """Returns (holdings_list, summary_dict, meta)"""
    reader = csv.reader(csv_text.splitlines())
    rows = list(reader)

    header_idx = None
    for i, r in enumerate(rows):
        if any("公司名称" in c for c in r):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("CSV 缺少表头")

    # exchange rates
    rates = {}
    for i in range(0, header_idx):
        line = ",".join(rows[i])
        for m in re.finditer(r"(US|HK|RMB)\s*>\s*RMB[,\s]*([\d.]+)", line):
            rates[m.group(1)] = float(m.group(2))

    # date
    doc_date = None
    for i in range(header_idx-1, max(header_idx-5,-1), -1):
        if i < 0: break
        for c in rows[i]:
            m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", c)
            if m:
                doc_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                break
        if doc_date: break

    positions = []
    summary = {}
    regions = {}
    past_total = False

    LABELS = {"年初":"year_start","工资结余":"salary_surplus","基数":"base",
              "收益":"total_pnl","收益率":"total_roi"}

    for i in range(header_idx+1, len(rows)):
        row = rows[i]
        while len(row) < 14: row.append("")
        market = row[1].strip()
        name = row[2].strip()
        code = row[3].strip() if len(row) > 3 else ""
        col8 = row[9].strip() if len(row) > 9 else ""

        # Totals row
        if not past_total and ("总计" in name or "总计" in market):
            summary["doc_invested"] = parse_amount(row[11])  # col 11 = 投入
            summary["doc_current"] = parse_amount(row[12])  # col 12 = 当前
            summary["doc_dividends"] = parse_amount(row[13]) if len(row) > 13 else None
            past_total = True
            continue

        # Summary area
        if past_total:
            if col8 in ("整体","国内","境外"):
                regions[col8] = {
                    "invested": parse_amount(row[10]),  # adjusted cols with code added
                    "current": parse_amount(row[11]),
                    "pnl": parse_amount(row[12]) if len(row) > 12 else None,
                }
            if market in LABELS:
                val = parse_amount(row[2])
                if val is None: val = parse_percent(row[2])
                summary[LABELS[market]] = val
                # also check for 境外 region on same row
                c8 = row[9].strip() if len(row) > 9 else ""
                if c8 in ("整体","国内","境外"):
                    regions[c8] = {
                        "invested": parse_amount(row[10]),
                        "current": parse_amount(row[11]),
                        "pnl": parse_amount(row[12]) if len(row) > 12 else None,
                    }
                continue
            if "LC26" in market or "信用卡" in name: break
            continue

        # Position rows
        if not name: continue
        if name in ("现金","年初","工资结余","基数","收益","收益率","EXP:"): continue
        if name.startswith("ps：") or name.startswith("信用卡"): continue

        # code is in col[3]; everything shifted right by 1
        cost_raw = row[4].strip() or None
        qty = parse_qty(row[9])
        invested = parse_amount(row[10])
        dividends = parse_amount(row[13]) if len(row) > 13 else None

        positions.append({
            "market": market or None,
            "name": name,
            "code": code if code else None,
            "cost_raw": cost_raw,
            "cost": parse_amount(row[4]),
            "qty": qty,
            "invested": invested,
            "dividends": dividends,
        })

    summary["regions"] = regions
    meta = {"doc_date": doc_date, "exchange_rates": rates}
    return positions, summary, meta


def build_snapshot(positions, summary, prices):
    """Compute current values from live prices, generate full snapshot dict"""
    rates = summary.get("exchange_rates", {})
    usd_rate = rates.get("US", 6.78)
    hkd_rate = rates.get("HK", 0.86)

    holdings = []
    total_inv = 0
    total_cur = 0

    for p in positions:
        code = p["code"]
        mkt = p["market"]
        qty = p["qty"] or 0
        inv = p["invested"] or 0

        # Live price
        live_price = prices.get(code) if code else None
        fx = 1 if mkt == "CN" else (hkd_rate if mkt == "HK" else usd_rate)

        if live_price and qty:
            cur = round(qty * live_price * fx, 2)
        else:
            cur = inv  # fallback to invested

        pnl = round(cur - inv, 2)
        roi = round(pnl / inv * 100, 4) if inv else None

        holdings.append({
            "market": mkt,
            "currency": {"CN":"CNY","HK":"HKD","US":"USD"}.get(mkt),
            "name": p["name"],
            "code": code,
            "cost_price_raw": p["cost_raw"],
            "current_price_raw": str(live_price) if live_price else None,
            "cost_price": p["cost"],
            "current_price": live_price,
            "quantity": qty,
            "invested": inv,
            "current": cur,
            "pnl": pnl,
            "roi": roi,
            "dividends": p["dividends"],
            "pos_cost_pct": None,
            "pos_curr_pct": None,
        })
        total_inv += inv
        total_cur += cur

    # pos percentages
    for h in holdings:
        h["pos_cost_pct"] = round(h["invested"]/total_inv*100, 4) if total_inv else None
        h["pos_curr_pct"] = round(h["current"]/total_cur*100, 4) if total_cur else None

    pnl = round(total_cur - total_inv, 2)
    roi = round(pnl / total_inv * 100, 4) if total_inv else None

    # Regions
    cn_inv = sum(h["invested"] for h in holdings if h["market"]=="CN")
    cn_cur = sum(h["current"] for h in holdings if h["market"]=="CN")
    ov_inv = sum(h["invested"] for h in holdings if h["market"] in ("HK","US"))
    ov_cur = sum(h["current"] for h in holdings if h["market"] in ("HK","US"))

    # Cash from document (approximate: doc overall current - doc stock current)
    doc_regions = summary.get("regions", {})
    doc_overall_cur = doc_regions.get("整体", {}).get("current", total_cur)
    cash_net = round((doc_overall_cur or total_cur) - total_cur, 2)
    stock_cash = round(total_cur + cash_net, 2)

    regions_calc = {
        "整体": {"invested": total_inv, "current": stock_cash, "pnl": round(stock_cash - total_inv, 2)},
        "国内": {"invested": cn_inv,
                 "current": round(cn_cur + cash_net*(cn_cur/total_cur if total_cur else 1), 2),
                 "pnl": round(cn_cur - cn_inv + cash_net*(cn_cur/total_cur if total_cur else 1), 2)},
        "境外": {"invested": ov_inv,
                 "current": round(ov_cur + cash_net*(ov_cur/total_cur if total_cur else 1), 2),
                 "pnl": round(ov_cur - ov_inv + cash_net*(ov_cur/total_cur if total_cur else 1), 2)},
    }

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "snapshot_time": now.strftime("%Y-%m-%d %H:%M:%S +08:00"),
        "source": "westock-mcp 实时行情",
        "file_id": "fGemVXqsvRGM",
        "doc_date": summary.get("doc_date") or meta.get("doc_date"),
        "exchange_rates": {k:v for k,v in rates.items() if k in ("US","HK")} or None,
        "summary": {
            "holdings_pos_cost_pct": round(total_inv/total_inv*100,4) if total_inv else None,
            "holdings_pos_curr_pct": round(total_cur / stock_cash * 100, 2) if stock_cash else None,
            "holdings_roi": roi,
            "holdings_invested": total_inv,
            "holdings_current": total_cur,
            "holdings_pnl": pnl,
            "holdings_dividends": None,
            "year_start": summary.get("year_start"),
            "salary_surplus": summary.get("salary_surplus"),
            "base": summary.get("base"),
            "total_pnl": summary.get("total_pnl"),
            "total_roi": summary.get("total_roi"),
            "regions": regions_calc,
        },
        "holdings": holdings,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python snapshot_live.py <csv_file> <prices_json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        csv_text = f.read()
    with open(sys.argv[2], "r", encoding="utf-8") as f:
        prices = json.load(f)

    positions, summary, meta = parse_holdings(csv_text)
    meta["exchange_rates"] = summary.pop("exchange_rates", None)
    snapshot = build_snapshot(positions, summary, prices)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "portfolio_snapshots")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'{snapshot["date"]}.json')
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"[OK] {out_file}")
    h = snapshot["holdings"]
    s = snapshot["summary"]
    print(f"     持仓: {len(h)}只 | 投入: {s['holdings_invested']/10000:.1f}万 | 当前: {s['holdings_current']/10000:.1f}万")
    print(f"     收益: {s['holdings_pnl']/10000:+.1f}万 ({s['holdings_roi']:+.2f}%)")