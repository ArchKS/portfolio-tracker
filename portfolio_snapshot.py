# -*- coding: utf-8 -*-
"""
持仓每日快照工具
从腾讯文档导出的 CSV 数据中提取持仓信息，生成结构化 JSON 快照。

用法:
  python portfolio_snapshot.py <csv_file>          # 从 CSV 文件读取
  python portfolio_snapshot.py                      # 从 stdin 读取
"""

import csv
import json
import sys
import os
import re
from datetime import datetime, timezone, timedelta


# ── 解析工具函数 ──────────────────────────────────────────

def parse_amount(val):
    """解析金额字符串: '91.2万' -> 912000, '27754' -> 27754.0, '¥19.7' -> 19.7"""
    if not val or not val.strip():
        return None
    s = val.strip()
    # 去掉货币符号和逗号
    s = s.replace("¥", "").replace("HK$", "").replace("$", "").replace(",", "").strip()
    multiplier = 1.0
    if "万" in s:
        s = s.replace("万", "").strip()
        multiplier = 10000.0
    elif "亿" in s:
        s = s.replace("亿", "").strip()
        multiplier = 100000000.0
    try:
        return round(float(s) * multiplier, 2)
    except ValueError:
        return None


def parse_percent(val):
    """解析百分比: '-10.1%' -> -10.1, '37.8%' -> 37.8"""
    if not val or not val.strip():
        return None
    s = val.strip().replace("%", "").replace(",", "")
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def parse_quantity(val):
    """解析持有数量: '46200 ' -> 46200"""
    if not val or not val.strip():
        return None
    s = val.strip().replace(",", "")
    try:
        return int(float(s))
    except ValueError:
        return None


def extract_currency(price_str):
    """从价格字符串提取货币: '¥19.7' -> 'CNY', 'HK$96.4' -> 'HKD', '$20.8' -> 'USD'"""
    if not price_str or not price_str.strip():
        return None
    s = price_str.strip()
    if s.startswith("HK$"):
        return "HKD"
    if s.startswith("¥"):
        return "CNY"
    if s.startswith("$"):
        return "USD"
    return None


MARKET_CURRENCY = {
    "CN": "CNY",
    "HK": "HKD",
    "US": "USD",
}


# ── 核心解析逻辑 ──────────────────────────────────────────

def parse_holdings(csv_text):
    """解析 CSV 文本，返回 (holdings, summary, meta)"""
    reader = csv.reader(csv_text.splitlines())
    rows = list(reader)

    # 定位表头行（含"公司名称"）
    header_idx = None
    for i, row in enumerate(rows):
        if any("公司名称" in cell for cell in row):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("CSV 中未找到表头行（缺少'公司名称'）")

    # 提取日期（表头上方通常有一行带日期）
    snapshot_date = None
    for i in range(header_idx - 1, max(header_idx - 5, -1), -1):
        if i < 0:
            break
        for cell in rows[i]:
            m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", cell)
            if m:
                snapshot_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                break
        if snapshot_date:
            break

    # 提取汇率信息
    exchange_rates = {}
    for i in range(0, header_idx):
        if i >= len(rows):
            break
        row = rows[i]
        line = ",".join(row)
        for m in re.finditer(r"(US|HK|RMB)\s*>\s*RMB[,\s]*([\d.]+)", line):
            exchange_rates[m.group(1)] = float(m.group(2))

    # 解析持仓行 + 汇总区域
    holdings = []
    summary = {}
    regions = {}

    # 汇总标签 → 字段名映射（总计行之后的区域）
    SUMMARY_LABELS = {
        "年初": "year_start",
        "工资结余": "salary_surplus",
        "基数": "base",
        "收益": "total_pnl",       # 文档中的总收益（含现金等，非纯持仓）
        "收益率": "total_roi",     # 文档中的总收益率
    }

    past_total = False  # 是否已过"总计"行

    for i in range(header_idx + 1, len(rows)):
        row = rows[i]
        # 补齐列数
        while len(row) < 13:
            row.append("")

        market = row[1].strip()
        name = row[2].strip()
        col8 = row[8].strip()  # 区域标签列（整体/国内/境外）

        # ── 总计行：持仓表自身的汇总 ──
        if not past_total and ("总计" in name or "总计" in market):
            summary["holdings_pos_cost_pct"] = parse_percent(row[5])
            summary["holdings_pos_curr_pct"] = parse_percent(row[6])
            summary["holdings_roi"] = parse_percent(row[7])
            summary["holdings_invested"] = parse_amount(row[9])
            summary["holdings_current"] = parse_amount(row[10])
            if summary["holdings_invested"] is not None and summary["holdings_current"] is not None:
                summary["holdings_pnl"] = round(summary["holdings_current"] - summary["holdings_invested"], 2)
            summary["holdings_dividends"] = parse_amount(row[12])
            past_total = True
            continue

        # ── 总计行之后的汇总区域 ──
        if past_total:
            # 右侧：区域标签在 col[8]，投入/当前/收益在 col[9-11]
            # （优先检查，因为某些行同时含左侧标签和右侧区域数据）
            if col8 in ("整体", "国内", "境外"):
                regions[col8] = {
                    "invested": parse_amount(row[9]),
                    "current": parse_amount(row[10]),
                    "pnl": parse_amount(row[11]),
                }

            # 左侧：标签在 col[1]，值在 col[2]（年初/工资结余/基数/收益/收益率）
            if market in SUMMARY_LABELS:
                val = parse_amount(row[2])
                if val is None:
                    val = parse_percent(row[2])
                summary[SUMMARY_LABELS[market]] = val
                continue

            # 到达期权/信用卡等无关区域时停止
            if "LC26" in market or "信用卡分期" in name or "购买日期" in market:
                break
            # 跳过空行和现金明细行
            if not any(cell.strip() for cell in row):
                continue
            continue

        # ── 持仓行（总计之前）──
        if not name:
            continue
        if name in ("现金", "年初", "工资结余", "基数", "收益", "收益率", "EXP:"):
            continue
        if name.startswith("ps：") or name.startswith("信用卡"):
            continue

        holding = {
            "market": market or None,
            "currency": MARKET_CURRENCY.get(market, extract_currency(row[3].strip())),
            "name": name,
            "cost_price_raw": row[3].strip() or None,
            "current_price_raw": row[4].strip() or None,
            "cost_price": parse_amount(row[3]),
            "current_price": parse_amount(row[4]),
            "pos_cost_pct": parse_percent(row[5]),   # 占成本比
            "pos_curr_pct": parse_percent(row[6]),   # 占当前比
            "roi": parse_percent(row[7]),             # 盈亏%
            "quantity": parse_quantity(row[8]),
            "invested": parse_amount(row[9]),          # 投入（已换算为 RMB）
            "current": parse_amount(row[10]),          # 当前（已换算为 RMB）
            "dividends": parse_amount(row[12]),        # 收到股息
        }

        # 计算收益金额
        if holding["invested"] is not None and holding["current"] is not None:
            holding["pnl"] = round(holding["current"] - holding["invested"], 2)
        else:
            holding["pnl"] = None

        holdings.append(holding)

    if regions:
        summary["regions"] = regions

    meta = {
        "snapshot_date_in_doc": snapshot_date,
        "exchange_rates": exchange_rates if exchange_rates else None,
    }

    return holdings, summary, meta


# ── 主入口 ────────────────────────────────────────────────

def main():
    # 读取 CSV
    if len(sys.argv) >= 2:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            csv_text = f.read()
    else:
        csv_text = sys.stdin.read()

    if not csv_text.strip():
        print("Error: CSV 数据为空", file=sys.stderr)
        sys.exit(1)

    holdings, summary, meta = parse_holdings(csv_text)

    # 生成快照
    tz = timezone(timedelta(hours=8))  # UTC+8
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")

    snapshot = {
        "date": today,
        "snapshot_time": now.strftime("%Y-%m-%d %H:%M:%S +08:00"),
        "source": "腾讯文档-持仓",
        "file_id": "fGemVXqsvRGM",
        "doc_date": meta["snapshot_date_in_doc"],
        "exchange_rates": meta["exchange_rates"],
        "summary": summary,
        "holdings": holdings,
    }

    # 输出目录：脚本同级 portfolio_snapshots/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "portfolio_snapshots")
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, f"{today}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # 控制台摘要
    print(f"[OK] 快照已保存: {output_file}")
    print(f"     持仓数量: {len(holdings)}")
    if summary:
        tp = summary.get("total_pnl")
        tr = summary.get("total_roi")
        ys = summary.get("year_start")
        base = summary.get("base")
        hi = summary.get("holdings_invested")
        hc = summary.get("holdings_current")
        hp = summary.get("holdings_pnl")
        hr = summary.get("holdings_roi")
        hd = summary.get("holdings_dividends")
        print(f"     ── 文档汇总 ──")
        print(f"     总收益:   {tp:>,.2f}" if tp is not None else "     总收益:   N/A")
        print(f"     总收益率: {tr}%" if tr is not None else "     总收益率: N/A")
        if ys is not None:
            print(f"     年初:     {ys:>,.2f}")
        if base is not None:
            print(f"     基数:     {base:>,.2f}")
        print(f"     ── 持仓汇总 ──")
        print(f"     持仓投入: {hi:>,.2f}" if hi is not None else "     持仓投入: N/A")
        print(f"     持仓当前: {hc:>,.2f}" if hc is not None else "     持仓当前: N/A")
        print(f"     持仓收益: {hp:>,.2f}" if hp is not None else "     持仓收益: N/A")
        print(f"     持仓收益率: {hr}%" if hr is not None else "     持仓收益率: N/A")
        print(f"     持仓股息: {hd:>,.2f}" if hd is not None else "     持仓股息: N/A")


if __name__ == "__main__":
    main()
