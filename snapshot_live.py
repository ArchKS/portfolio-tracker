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

def parse_amount(val, nd=2):
    if not val or not val.strip(): return None
    s = val.strip().replace("¥","").replace("HK$","").replace("$","").replace(",","")
    m = 1.0
    if "万" in s: s = s.replace("万","").strip(); m = 10000
    elif "亿" in s: s = s.replace("亿","").strip(); m = 1e8
    try: return round(float(s) * m, nd)
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
        orig_len = len(row)  # before padding — needed to right-align short rows
        while len(row) < 14: row.append("")
        market = row[1].strip()
        name = row[2].strip()
        code = row[3].strip() if len(row) > 3 else ""
        col8 = row[8].strip() if len(row) > 8 else ""

        # Totals row — data is left-aligned: col5=投入, col6=当前, col7=股息
        if not past_total and ("总计" in name or "总计" in market):
            summary["doc_invested"] = parse_amount(row[5])
            summary["doc_current"] = parse_amount(row[6])
            summary["doc_dividends"] = parse_amount(row[7]) if len(row) > 7 else None
            past_total = True
            continue

        # Summary area
        if past_total:
            if col8 in ("整体","国内","境外"):
                regions[col8] = {
                    "invested": parse_amount(row[9]),
                    "current": parse_amount(row[10]),
                    "pnl": parse_amount(row[11]) if len(row) > 11 else None,
                }
            if market in LABELS:
                key = LABELS[market]
                if key == "total_roi":
                    val = parse_percent(row[2])
                    if val is not None: val = round(val * 100, 2)
                else:
                    val = parse_amount(row[2])
                    if val is None: val = parse_percent(row[2])
                summary[key] = val
                # also check for 境外 region on same row
                c8 = row[8].strip() if len(row) > 8 else ""
                if c8 in ("整体","国内","境外"):
                    regions[c8] = {
                        "invested": parse_amount(row[9]),
                        "current": parse_amount(row[10]),
                        "pnl": parse_amount(row[11]) if len(row) > 11 else None,
                    }
                continue
            if "LC26" in market or "信用卡" in name: break
            continue

        # Position rows
        if not name: continue
        if name in ("现金","年初","工资结余","基数","收益","收益率","EXP:"): continue
        if name.startswith("ps：") or name.startswith("信用卡"): continue

        # Fix short rows: e.g. SMMT Call has only 5 cols, data shifted left
        if code and not re.match(r'^\d{4,6}\.(SH|SZ|HK)$', code) and not re.match(r'^[A-Z]+\.US$', code):
            # Not a valid stock code → pad so the row's LAST value aligns with 当前 (col11)
            # Handles both [名称,投入,当前] and [名称,pos/curr,投入,当前] short rows
            pad_needed = 11 - (orig_len - 1)
            if pad_needed > 0:
                row = row[:3] + [''] * pad_needed + row[3:]
            while len(row) < 14: row.append("")
            code = row[3].strip() if len(row) > 3 else ""
            name = row[2].strip() if len(row) > 2 else ""

        # code is in col[3]; everything shifted right by 1
        cost_raw = row[4].strip() or None
        qty = parse_qty(row[9])
        invested = parse_amount(row[10])
        dividends = parse_amount(row[12]) if len(row) > 12 else None

        positions.append({
            "market": market or None,
            "name": name,
            "code": code if code else None,
            "cost_raw": cost_raw,
            "cost": parse_amount(row[4], 4),
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
        # 收益率直接用现价和成本价计算（纯股价涨幅，不受汇率/数量影响）
        if live_price and p["cost"]:
            roi = round((live_price - p["cost"]) / p["cost"] * 100, 4)
        else:
            roi = None

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

    # Use 整体 (overall, incl. cash adjustment) as denominator to match document's pos/cost & pos/curr
    doc_regions = summary.get("regions", {})
    overall_inv = doc_regions.get("整体", {}).get("invested") or total_inv
    # Live overall current = live stock current + fixed cash difference from document
    doc_overall_cur = doc_regions.get("整体", {}).get("current") or total_cur
    doc_stock_cur = summary.get("doc_current") or total_cur
    cash_diff = round(doc_overall_cur - doc_stock_cur, 2)  # fixed cash adjustment
    overall_cur = round(total_cur + cash_diff, 2)  # live overall current

    # pos percentages
    for h in holdings:
        h["pos_cost_pct"] = round(h["invested"]/overall_inv*100, 4) if overall_inv else None
        h["pos_curr_pct"] = round(h["current"]/overall_cur*100, 4) if overall_cur else None

    pnl = round(total_cur - total_inv, 2)
    roi = round(pnl / total_inv * 100, 4) if total_inv else None

    # Regions
    cn_inv = sum(h["invested"] for h in holdings if h["market"]=="CN")
    cn_cur = sum(h["current"] for h in holdings if h["market"]=="CN")
    ov_inv = sum(h["invested"] for h in holdings if h["market"] in ("HK","US"))
    ov_cur = sum(h["current"] for h in holdings if h["market"] in ("HK","US"))

    regions_calc = {
        "整体": {"invested": overall_inv, "current": overall_cur, "pnl": round(overall_cur - overall_inv, 2)},
        "国内": {"invested": cn_inv,
                 "current": round(cn_cur + cash_diff*(cn_cur/total_cur if total_cur else 1), 2),
                 "pnl": round(cn_cur - cn_inv + cash_diff*(cn_cur/total_cur if total_cur else 1), 2)},
        "境外": {"invested": ov_inv,
                 "current": round(ov_cur + cash_diff*(ov_cur/total_cur if total_cur else 1), 2),
                 "pnl": round(ov_cur - ov_inv + cash_diff*(ov_cur/total_cur if total_cur else 1), 2)},
    }

    # Self-calculated total P&L and ROI (not from document)
    base = summary.get("base")
    total_pnl = round(overall_cur - base, 2) if base else None
    total_roi = round(total_pnl / base * 100, 2) if (base and total_pnl is not None) else None

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
            "holdings_pos_cost_pct": round(total_inv/overall_inv*100,4) if overall_inv else None,
            "holdings_pos_curr_pct": round(total_cur / overall_cur * 100, 2) if overall_cur else None,
            "holdings_roi": roi,
            "holdings_invested": total_inv,
            "holdings_current": total_cur,
            "holdings_pnl": pnl,
            "holdings_dividends": sum(h["dividends"] or 0 for h in holdings),
            "year_start": summary.get("year_start"),
            "salary_surplus": summary.get("salary_surplus"),
            "base": base,
            "total_pnl": total_pnl,
            "total_roi": total_roi,
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
    # 汇率由 parse_holdings 放入 meta；build_snapshot 从 summary 读取，需先转存
    summary["exchange_rates"] = meta.get("exchange_rates") or summary.pop("exchange_rates", None)
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