#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 7 张历史持仓截图整理成 portfolio_snapshots/YYYY-MM-DD.json。
部分模糊数据根据合计/盈亏率做了合理推断，见各日期注释。
"""
import json
import os
from datetime import datetime, timezone
from portfolio_snapshot import parse_amount, parse_percent

OUT_DIR = os.path.join(os.path.dirname(__file__), "portfolio_snapshots")

EXCHANGE_RATES = {"US": 6.7807, "HK": 0.8642}


def w(val):
    """把'万'为单位的数值转换为元。"""
    if val is None:
        return None
    return round(val * 10000, 2)


def pct(val):
    """百分比数值，保留两位小数。"""
    if val is None:
        return None
    return round(val, 2)


def make_holding(market, name, cost_raw, current_raw, pos_cost, pos_curr, roi, qty, invested_wan, current_wan, dividends_wan=None):
    """构造单只持仓记录（金额单位为万）。"""
    # 货币推断
    currency = {"CN": "CNY", "HK": "HKD", "US": "USD", "FU": "CNY", "OP": "CNY"}.get(market, "CNY")
    cost = parse_amount(cost_raw)
    current = parse_amount(current_raw)
    invested = w(invested_wan)
    current_val = w(current_wan)
    pnl = round(current_val - invested, 2) if invested is not None and current_val is not None else None
    return {
        "market": market,
        "currency": currency,
        "name": name,
        "cost_price_raw": cost_raw,
        "current_price_raw": current_raw,
        "cost_price": cost,
        "current_price": current,
        "pos_cost_pct": pct(pos_cost),
        "pos_curr_pct": pct(pos_curr),
        "roi": pct(roi),
        "quantity": qty,
        "invested": invested,
        "current": current_val,
        "dividends": w(dividends_wan) if dividends_wan is not None else None,
        "pnl": pnl,
    }


def calc_regions(holdings, stock_cash_wan, regions_override=None):
    """
    按持仓市场划分国内/境外，并把现金净额按持仓市值比例分配到各区域。
    若图片直接给了国内/境外分项（regions_override），则优先使用。
    返回以元为单位的 regions 字典。
    """
    total_invested = sum(h["invested"] or 0 for h in holdings)
    total_current = sum(h["current"] or 0 for h in holdings)

    if regions_override:
        return {
            k: {
                "invested": round(v["invested"] * 10000, 2),
                "current": round(v["current"] * 10000, 2),
                "pnl": round(v["pnl"] * 10000, 2),
            }
            for k, v in regions_override.items()
        }

    domestic = {"invested": 0.0, "current": 0.0}
    overseas = {"invested": 0.0, "current": 0.0}
    for h in holdings:
        if h["market"] == "CN":
            domestic["invested"] += h["invested"] or 0
            domestic["current"] += h["current"] or 0
        else:
            overseas["invested"] += h["invested"] or 0
            overseas["current"] += h["current"] or 0

    cash_net = stock_cash_wan * 10000 - total_current
    if total_current > 0 and cash_net != 0:
        domestic["current"] += cash_net * (domestic["current"] / total_current)
        overseas["current"] += cash_net * (overseas["current"] / total_current)

    regions = {
        "整体": {"invested": round(total_invested, 2), "current": round(stock_cash_wan * 10000, 2), "pnl": round(stock_cash_wan * 10000 - total_invested, 2)},
        "国内": {"invested": round(domestic["invested"], 2), "current": round(domestic["current"], 2), "pnl": round(domestic["current"] - domestic["invested"], 2)},
        "境外": {"invested": round(overseas["invested"], 2), "current": round(overseas["current"], 2), "pnl": round(overseas["current"] - overseas["invested"], 2)},
    }
    return regions


def build_snapshot(date_str, doc_date, holdings, year_start, salary_surplus, base,
                   total_pnl, total_roi, stock_cash_wan, dividends_wan=0,
                   regions_override=None):
    """构造单日快照字典。"""
    total_invested = sum(h["invested"] or 0 for h in holdings)
    total_current = sum(h["current"] or 0 for h in holdings)
    holdings_pnl = round(total_current - total_invested, 2)
    holdings_roi = pct((total_current - total_invested) / total_invested * 100) if total_invested else None

    # 持有占比按当前值估算
    for h in holdings:
        if total_current and h["current"] is not None:
            h["pos_curr_pct"] = pct(h["current"] / total_current * 100)
        if total_invested and h["invested"] is not None:
            h["pos_cost_pct"] = pct(h["invested"] / total_invested * 100)

    snapshot = {
        "date": date_str,
        "snapshot_time": datetime.strptime(date_str, "%Y-%m-%d").replace(hour=15, tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S +08:00"),
        "source": "历史截图整理",
        "doc_date": doc_date,
        "exchange_rates": EXCHANGE_RATES,
        "summary": {
            "holdings_pos_cost_pct": None,
            "holdings_pos_curr_pct": None,
            "holdings_roi": holdings_roi,
            "holdings_invested": round(total_invested, 2),
            "holdings_current": round(total_current, 2),
            "holdings_pnl": holdings_pnl,
            "holdings_dividends": w(dividends_wan),
            "year_start": w(year_start),
            "salary_surplus": w(salary_surplus),
            "base": w(base),
            "total_pnl": w(total_pnl),
            "total_roi": pct(total_roi),
            "regions": calc_regions(holdings, stock_cash_wan, regions_override),
        },
        "holdings": holdings,
    }
    return snapshot


def save_snapshot(snapshot):
    path = os.path.join(OUT_DIR, f"{snapshot['date']}.json")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


# ============================================================================
# 2026-03-30：无收益/收益率，用其他日期的年初250.5、工资结余15.0、基数258.0推算
# 收益 = 股票+现金252.4 - 250.5 - 15.0 = -13.1；收益率 = -13.1 / 258.0 = -5.08%
# ============================================================================
snap_0330 = build_snapshot(
    "2026-03-30", "2026/3/30",
    holdings=[
        make_holding("CN", "中矿资源", "¥31.0", "¥73.47", None, 40.8, 137.0, 14000, 43.4, 102.9),
        make_holding("CN", "LC2701", "16.0万", "1.7万", 13.9, 0.0, None, 5, 35.0, 35.0),
        make_holding("HK", "天齐锂业", "HK$43.5", "HK$47.8", 13.7, 9.8, None, 8200, 31.5, 34.6),
        make_holding("US", "传奇生物", "$24.6", "$17.05", 11.7, -30.7, None, 2500, 42.5, 29.5),
        make_holding("CN", "LC2607 C180000", "1.9万", "1.7万", 5.5, -7.9, None, 8, 15.0, 13.9),
        make_holding("US", "SQQQ PUT", "$10.0", "11.32", 2.5, 13.2, None, 800, 5.5, 6.3),
        make_holding("CN", "生猪2609", "1.3万", "1.2万", 0.5, None, None, 1, 1.3, 1.2),
    ],
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=-13.1, total_roi=-5.08, stock_cash_wan=252.4,
)

# ============================================================================
# 2026-05-08
# ============================================================================
snap_0508 = build_snapshot(
    "2026-05-08", "2026/5/8",
    holdings=[
        make_holding("HK", "天齐锂业", "HK$47.1", "HK$63.9", 49.7, 35.7, None, 24600, 100.7, 136.6),
        make_holding("FU", "LC2701", "16.0万", "14.0万", 12.4, 6.3, None, 4, 32.0, 34.0),
        make_holding("OP", "LC2607_C18000", "1.2万", "2.3万", 0.0, 101.6, None, 20, 23.2, 0.0),
        make_holding("CN", "海螺水泥", "¥21.7", "¥21.06", 20.4, -3.1, None, 26600, 57.8, 56.0),
        make_holding("US", "传奇生物", "$27.3", "$28.57", 14.9, 4.7, None, 2100, 39.0, 40.8),
        make_holding("HK", "同仁堂国药", "HK$7.7", "HK$7.4", 1.6, -3.4, None, 7000, 4.7, 4.5),
        make_holding("HK", "中海物业", "HK$4.0", "HK$4.1", 0.6, 1.8, None, 5000, 1.7, 1.8),
        make_holding("HK", "保利物业", "HK$31.2", "HK$31.9", 0.4, 2.4, None, 400, 1.1, 1.1),
        make_holding("HK", "中国民航", "HK$9.9", "HK$10.0", 0.3, 1.0, None, 1000, 0.9, 0.9),
        make_holding("CN", "青松建化", "¥4.1", "¥4.08", 0.3, -0.7, None, 2200, 0.9, 0.9),
        make_holding("HK", "泡泡玛特", "HK$172.0", "HK$171.4", 0.0, -0.3, None, 0, 0.0, 0.0),
        make_holding("HK", "腾讯控股", "HK$470.0", "HK$470.4", 0.0, 0.1, None, 0, 0.0, 0.0),
        make_holding("CN", "中矿资源", "¥31.0", "¥89.82", 0.0, 0.0, None, 0, 0.0, 0.0),
    ],
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=9.1, total_roi=3.51, stock_cash_wan=274.6,
)

# ============================================================================
# 2026-05-20：截图最模糊，个股投入/当前根据盈亏率反推并按合计150.8/150.8缩放
# 原始识别值缩放因子≈0.615，以保证总投入/总当前与图片总计一致
# ============================================================================
raw_0520 = [
    make_holding("FU", "LC2701", "16.0万", "15.0万", None, None, 1.3, 1, 36.4, 36.9),
    make_holding("OP", "LC26009_C200000", "1.3万", "0.0万", None, None, 0.0, 27, 36.4, 36.4),
    make_holding("US", "传奇生物", "$27.3", "$27.66", None, None, 1.3, 2100, 39.0, 39.5),
    make_holding("CN", "海螺水泥", "¥21.6", "¥20.01", None, None, -7.3, 31200, 67.4, 62.4),
    make_holding("CN", "青松建化", "¥4.1", "¥3.92", None, None, -4.6, 24600, 10.1, 9.6),
    make_holding("HK", "保利物业", "HK$31.9", "HK$30.6", None, None, -4.1, 3800, 10.5, 10.1),
    make_holding("HK", "中海物业", "HK$4.1", "HK$3.8", None, None, -6.6, 30000, 10.1, 9.9),
    make_holding("HK", "中国民航", "HK$9.7", "HK$9.5", None, None, -2.5, 12000, 10.1, 9.9),
    make_holding("HK", "同仁堂国药", "HK$7.5", "HK$7.2", None, None, -4.3, 15000, 9.8, 9.4),
    make_holding("HK", "腾讯控股", "HK$455.2", "HK$445.2", None, None, -2.2, 0, 2.7, 2.6),
    make_holding("HK", "泡泡玛特", "HK$156.0", "HK$151.9", None, None, -2.6, 200, 2.7, 2.6),
]
# 截图较模糊，个股数据保留原始识别值，不强制缩放。
# 图片中"合计投入/当前150.8万"口径不明，可能与个股加总不同；
# 报告中的资产/仓位走势使用 stock_cash=231.4 万，不受个股加总影响。
snap_0520 = build_snapshot(
    "2026-05-20", "2026/5/20",
    holdings=raw_0520,
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=-34.1, total_roi=-13.21, stock_cash_wan=231.4, dividends_wan=3.6,
)

# ============================================================================
# 2026-06-02
# ============================================================================
snap_0602 = build_snapshot(
    "2026-06-02", "2026/6/2",
    holdings=[
        make_holding("CN", "海螺水泥", "¥21.8", "¥20.11", 24.9, 24.0, -7.3, 28000, 61.1, 56.3),
        make_holding("US", "传奇生物", "$27.2", "$25.51", 15.0, 14.7, -6.2, 2000, 36.7, 34.5),
        make_holding("HK", "保利物业", "HK$32.0", "HK$28.7", 5.0, 4.6, -10.3, 4400, 12.1, 10.9),
        make_holding("HK", "中海物业", "HK$4.1", "HK$3.9", 4.3, 4.2, -5.5, 30000, 10.5, 10.0),
        make_holding("HK", "中国民航", "HK$9.7", "HK$9.3", 5.1, 5.1, -4.0, 15000, 12.5, 12.1),
        make_holding("HK", "同仁堂国药", "HK$7.4", "HK$7.0", 5.4, 5.4, -4.5, 21000, 13.3, 12.7),
        make_holding("HK", "西锐", "HK$37.3", "HK$37.8", 3.9, 4.2, 1.2, 3000, 9.7, 9.8),
        make_holding("HK", "康方生物", "HK$118.5", "HK$93.6", 8.6, 6.9, -21.0, 2000, 20.8, 16.2),
        make_holding("HK", "再鼎医药", "HK$13.4", "HK$13.5", 4.2, 4.5, 0.6, 9000, 10.4, 10.5),
    ],
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=-30.6, total_roi=-11.85, stock_cash_wan=234.9, dividends_wan=3.5,
)

# ============================================================================
# 2026-06-05：图片直接给出国内/境外分项
# ============================================================================
snap_0605 = build_snapshot(
    "2026-06-05", "2026/6/5",
    holdings=[
        make_holding("CN", "海螺水泥", "¥21.8", "¥19.35", 25.3, 23.1, -11.3, 28000, 61.1, 54.2),
        make_holding("US", "传奇生物", "$26.9", "$33.97", 14.3, 18.7, 26.4, 1900, 34.6, 43.8),
        make_holding("HK", "康方生物", "HK$120.4", "HK$93.6", 8.6, 6.9, -22.3, 2000, 20.8, 16.2),
        make_holding("HK", "再鼎医药", "HK$13.2", "HK$12.6", 7.6, 7.4, -4.6, 16000, 18.3, 17.5),
        make_holding("HK", "同仁堂国药", "HK$7.4", "HK$7.0", 5.5, 5.4, -5.2, 21000, 13.4, 12.7),
        make_holding("HK", "中国民航", "HK$9.7", "HK$9.0", 5.2, 5.0, -6.9, 15000, 12.2, 11.7),
        make_holding("HK", "保利物业", "HK$32.1", "HK$28.5", 5.1, 4.6, -11.3, 4400, 12.2, 10.9),
        make_holding("HK", "中海物业", "HK$4.1", "HK$3.7", 4.4, 4.1, -8.4, 30000, 10.5, 9.6),
    ],
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=-23.2, total_roi=-9.01, stock_cash_wan=234.8, dividends_wan=3.5,
    regions_override={
        "整体": {"invested": 241.8, "current": 234.8, "pnl": -7.1},
        "国内": {"invested": 207.2, "current": 191.0, "pnl": -16.2},
        "境外": {"invested": 34.6, "current": 43.8, "pnl": 9.2},
    },
)

# ============================================================================
# 2026-07-01：图片直接给出国内/境外分项
# ============================================================================
snap_0701 = build_snapshot(
    "2026-07-01", "2026/7/1",
    holdings=[
        make_holding("CN", "海螺水泥", "¥20.4", "¥17.25", 38.7, 36.3, -15.4, 45500, 92.8, 78.5),
        make_holding("HK", "康方生物", "HK$97.2", "HK$88.1", 21.0, 21.1, -9.4, 6000, 50.4, 45.7),
        make_holding("US", "传奇生物", "$22.9", "$29.45", 5.8, 8.3, 28.7, 900, 14.0, 18.0),
        make_holding("HK", "再鼎医药", "HK$13.5", "HK$14.5", 2.3, 2.7, 6.8, 4700, 5.5, 5.9),
        make_holding("HK", "亚盛医药", "HK$34.0", "HK$33.2", 2.9, 3.2, -2.4, 2400, 7.1, 6.9),
        make_holding("HK", "药明合联", "HK$47.9", "HK$57.1", 0.9, 1.1, 19.0, 500, 2.1, 2.5),
        make_holding("HK", "中国民航", "HK$10.0", "HK$8.1", 5.1, 4.5, -19.2, 14000, 12.1, 9.8),
        make_holding("US", "PDD", "$81.5", "$81.20", 6.9, 7.6, -0.3, 300, 16.6, 16.5),
        make_holding("HK", "同仁堂国药", "HK$7.3", "HK$6.5", 6.8, 6.7, -11.0, 26000, 16.4, 14.6),
        make_holding("HK", "保利物业", "HK$40.7", "HK$25.8", 2.4, 1.6, -36.7, 1600, 5.6, 3.6),
        make_holding("HK", "中海物业", "HK$4.5", "HK$3.2", 3.3, 2.6, -28.9, 20000, 7.9, 5.6),
        make_holding("US", "SMMT", "$14.6", "$14.59", 1.2, 1.4, -0.1, 300, 3.0, 3.0),
        make_holding("HK", "汇贤产业信托", "HK$0.416", "HK$0.390", 1.8, 1.9, -6.2, 120000, 4.3, 4.1),
    ],
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=-41.5, total_roi=-16.08, stock_cash_wan=216.5, dividends_wan=4.2,
    regions_override={
        "整体": {"invested": 239.7, "current": 216.5, "pnl": -23.2},
        "国内": {"invested": 209.2, "current": 182.0, "pnl": -27.2},
        "境外": {"invested": 30.5, "current": 34.5, "pnl": 4.0},
    },
)

# ============================================================================
# 2026-07-03：图片直接给出国内/境外分项
# ============================================================================
snap_0703 = build_snapshot(
    "2026-07-03", "2026/7/3",
    holdings=[
        make_holding("CN", "海螺水泥", "¥19.7", "¥17.14", 38.6, 35.1, -13.2, 46200, 91.2, 79.2),
        make_holding("CN", "罗普斯金", "¥4.9", "¥4.95", 0.6, 0.7, 0.8, 3000, 1.5, 1.5),
        make_holding("HK", "康方生物", "HK$97.3", "HK$102.4", 21.4, 23.5, 5.3, 6000, 50.4, 53.1),
        make_holding("US", "传奇生物", "$22.9", "$29.91", 5.9, 8.1, 30.8, 900, 14.0, 18.3),
        make_holding("HK", "再鼎医药", "HK$13.5", "HK$15.0", 2.3, 2.7, 11.0, 4700, 5.5, 6.1),
        make_holding("HK", "亚盛医药", "HK$34.0", "HK$36.9", 3.0, 3.4, 8.5, 2400, 7.1, 7.6),
        make_holding("HK", "药明合联", "HK$47.9", "HK$61.7", 0.9, 1.2, 28.7, 500, 2.1, 2.7),
        make_holding("HK", "中国民航", "HK$10.0", "HK$8.1", 5.1, 4.5, -18.6, 14000, 12.1, 9.8),
        make_holding("US", "PDD", "$81.5", "$82.39", 7.0, 7.4, 1.2, 300, 16.6, 16.8),
        make_holding("HK", "同仁堂国药", "HK$6.9", "HK$6.5", 6.6, 6.4, -6.8, 26000, 15.6, 14.5),
        make_holding("HK", "保利物业", "HK$40.8", "HK$26.6", 2.4, 1.6, -34.8, 1600, 5.6, 3.7),
        make_holding("HK", "中海物业", "HK$4.5", "HK$3.3", 3.3, 2.6, -26.7, 20000, 7.9, 5.8),
        make_holding("US", "SMMT", "$14.6", "$15.42", 1.3, 1.4, 5.6, 300, 3.0, 3.1),
        make_holding("HK", "汇贤产业信托", "HK$0.416", "HK$0.395", 1.8, 1.8, -5.0, 120000, 4.3, 4.1),
    ],
    year_start=250.5, salary_surplus=15.0, base=258.0,
    total_pnl=-32.5, total_roi=-12.59, stock_cash_wan=225.5, dividends_wan=4.1,
    regions_override={
        "整体": {"invested": 236.0, "current": 225.5, "pnl": -23.2},
        "国内": {"invested": 205.0, "current": 190.5, "pnl": -27.2},
        "境外": {"invested": 31.0, "current": 35.0, "pnl": 4.0},
    },
)


# ============================================================================
# 2026-01-01：基数=92.4万（年初86.5+工资11.6），把收益/收益率置零（作为新基准日）
# 4 只持仓（中矿/传奇/再鼎/QQQ PUT）；现金净额 -0.7万
# ============================================================================
snap_0101 = build_snapshot(
    "2026-01-01", "2026/1/1",
    holdings=[
        make_holding("CN", "中矿", "¥30.90", "¥78.55", 80.3, None, 154.5, 25600, 79.0, 201.1),
        make_holding("US", "传奇生物", "$26.10", "$21.53", None, 16.4, -17.6, 2724, 49.7, 41.0),
        make_holding("HK", "再鼎医药", "HK$14.3", "HK$13.7", None, 2.0, -4.5, 4000, 5.1, 4.9),
        make_holding("US", "QQQ 270115 300P", "$3.30", "$2.40", None, 1.7, -27.2, 2500, 5.8, 4.2),
    ],
    year_start=86.5, salary_surplus=11.6, base=92.4,
    total_pnl=0, total_roi=0, stock_cash_wan=250.5,
)

# ============================================================================
# 2026-03-10：基数=256.8万，收益-5.5万（-2.14%）
# 4 只持仓（中矿/传奇/再鼎/2605 C14000 期权）；现金净额 0
# ============================================================================
snap_0310 = build_snapshot(
    "2026-03-10", "2026/3/10",
    holdings=[
        make_holding("CN", "中矿", "¥29.6", "¥80.13", 54.8, 77.5, 170.3, 24900, 73.8, 199.5),
        make_holding("US", "传奇生物", "$25.3", "$19.14", 37.0, 14.6, -24.3, 2868, 49.8, 37.7),
        make_holding("HK", "再鼎医药", "HK$14.3", "HK$15.1", 8.2, 4.5, 5.3, 8800, 11.0, 11.6),
        make_holding("CN", "2605 C14000", "¥10800.00", "¥10800.00", 6.4, 3.4, 0.0, 8, 8.6, 8.6),
    ],
    year_start=250.5, salary_surplus=12.5, base=256.8,
    total_pnl=-5.5, total_roi=-2.14, stock_cash_wan=257.5,
)

# ============================================================================
# 2026-03-26：基数=256.8万，收益-33.2万（-12.92%）
# 5 只持仓（中矿/碳酸锂2701/2605 C14000/天齐锂业/传奇生物）；现金净额 -1.3万
# ============================================================================
snap_0326 = build_snapshot(
    "2026-03-26", "2026/3/26",
    holdings=[
        make_holding("CN", "中矿", "¥31.0", "¥68.22", 28.4, 49.3, 120.1, 16600, 51.5, 113.2),
        make_holding("CN", "碳酸锂2701", "¥16.0", "¥15.7", 22.1, 17.1, -1.9, 25000, 40.0, 39.3),
        make_holding("CN", "2605 C14000", "¥1.08", "¥1.20", 4.8, 4.2, 11.1, 80000, 8.6, 9.6),
        make_holding("HK", "天齐锂业", "HK$43.5", "HK$45.0", 17.4, 14.2, 3.4, 8200, 31.5, 32.6),
        make_holding("US", "传奇生物", "$24.6", "$17.60", 28.1, 15.9, -28.5, 3000, 51.0, 36.5),
    ],
    year_start=250.5, salary_surplus=12.5, base=256.8,
    total_pnl=-33.2, total_roi=-12.92, stock_cash_wan=229.9,
)


if __name__ == "__main__":
    for snap in [snap_0101, snap_0310, snap_0326, snap_0330, snap_0508, snap_0520, snap_0602, snap_0605, snap_0701, snap_0703]:
        save_snapshot(snap)
    print("done")
