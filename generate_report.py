# -*- coding: utf-8 -*-
"""
持仓收益分析报告生成器
读取 portfolio_snapshots/ 下所有 JSON 快照，生成自包含 HTML 报告。

用法:
  python generate_report.py
"""

import json
import os
import glob
import sys
from datetime import datetime, timedelta, timezone

from generate_timeline import generate_timeline_svg


# ── 数据处理 ──────────────────────────────────────────────

def load_snapshots(snap_dir):
    """读取所有快照 JSON，按日期排序"""
    files = sorted(glob.glob(os.path.join(snap_dir, "*.json")))
    snapshots = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            snapshots.append(json.load(fp))
    return snapshots


def calculate_drawdown(values):
    """从资产价值序列计算回撤"""
    if not values:
        return [], 0
    peak = values[0]
    drawdowns = []
    for v in values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100 if peak > 0 else 0
        drawdowns.append(round(dd, 2))
    max_dd = min(drawdowns) if drawdowns else 0
    return drawdowns, round(max_dd, 2)


def calculate_stats(snapshots):
    """计算统计指标"""
    if not snapshots:
        return {}

    latest = snapshots[-1]
    holdings = latest.get("holdings", [])
    summary = latest.get("summary", {})

    # 持仓级统计
    rois = [h for h in holdings if h.get("roi") is not None]
    pnls = [h for h in holdings if h.get("pnl") is not None]

    stats = {
        "snapshot_count": len(snapshots),
        "latest_date": latest.get("date", ""),
        "holdings_count": len(holdings),
    }

    if rois:
        best = max(rois, key=lambda h: h["roi"])
        worst = min(rois, key=lambda h: h["roi"])
        stats["max_roi_name"] = best["name"]
        stats["max_roi"] = best["roi"]
        stats["min_roi_name"] = worst["name"]
        stats["min_roi"] = worst["roi"]

    if pnls:
        best_p = max(pnls, key=lambda h: h["pnl"])
        worst_p = min(pnls, key=lambda h: h["pnl"])
        stats["max_pnl_name"] = best_p["name"]
        stats["max_pnl"] = best_p["pnl"]
        stats["min_pnl_name"] = worst_p["name"]
        stats["min_pnl"] = worst_p["pnl"]

    # 时间序列统计（需要多个快照）
    if len(snapshots) > 1:
        # 资产走势统一使用"整体"region的current（与图表中的资产走势一致）
        values = [s.get("summary", {}).get("regions", {}).get("整体", {}).get("current", 0) for s in snapshots]
        drawdowns, max_dd = calculate_drawdown(values)
        stats["max_drawdown"] = max_dd

        daily_returns = []
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                dr = (values[i] - values[i - 1]) / values[i - 1] * 100
                daily_returns.append(round(dr, 2))
        if daily_returns:
            stats["max_daily_return"] = max(daily_returns)
            stats["min_daily_return"] = min(daily_returns)
            stats["avg_daily_return"] = round(sum(daily_returns) / len(daily_returns), 2)

        # 连续盈亏
        streak_pos = 0
        streak_neg = 0
        max_streak_pos = 0
        max_streak_neg = 0
        for dr in daily_returns:
            if dr > 0:
                streak_pos += 1
                streak_neg = 0
                max_streak_pos = max(max_streak_pos, streak_pos)
            elif dr < 0:
                streak_neg += 1
                streak_pos = 0
                max_streak_neg = max(max_streak_neg, streak_neg)
        stats["max_streak_pos"] = max_streak_pos
        stats["max_streak_neg"] = max_streak_neg

    return stats


# ── 格式化工具 ────────────────────────────────────────────

def fmt_wan(val):
    """格式化为万元"""
    if val is None:
        return "—"
    wan = val / 10000
    if abs(wan) >= 1:
        return f"{wan:,.1f}万"
    return f"{val:,.0f}"


def fmt_pct(val):
    if val is None:
        return "—"
    return f"{val:+.2f}%"


def fmt_color(val, is_pct=False):
    """返回颜色 class"""
    if val is None:
        return ""
    if val > 0:
        return "profit"
    elif val < 0:
        return "loss"
    return ""


# ── HTML 生成 (Swiss Modernism 2.0) ───────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>持仓收益分析 — PORTFOLIO</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
:root{
  --paper:#ffffff;
  --ink:#111111;
  --ink-2:#5b5b5b;
  --ink-3:#9a9a9a;
  --rule:#e4e4e4;
  --rule-strong:#111111;
  --accent:#e4002b;      /* Swiss red */
  --profit:#e4002b;      /* 涨 = 红 */
  --loss:#007a33;        /* 跌 = 绿 */
  --pad:28px;
}
*{margin:0;padding:0;box-sizing:border-box;}
html,body{background:var(--paper);}
.chart-card{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;}
body{
  font-family:'Inter','Noto Sans SC',-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;
  color:var(--ink);
  line-height:1.5;
  font-feature-settings:"tnum" 1;
  -webkit-font-smoothing:antialiased;
  padding:var(--pad);
  max-width:1180px;
  margin:0 auto;
  touch-action:manipulation;
}
.up{color:var(--profit);}
.down{color:var(--loss);}

/* ── Masthead ── */
.masthead{border-bottom:3px solid var(--rule-strong);padding-bottom:18px;margin-bottom:36px;}
.masthead .kicker{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);font-weight:700;}
.masthead h1{font-size:42px;font-weight:800;letter-spacing:-.03em;line-height:1.04;margin-top:8px;}
.masthead .meta{margin-top:12px;font-size:13px;color:var(--ink-2);display:flex;gap:24px;flex-wrap:wrap;letter-spacing:.02em;}
.masthead .meta b{color:var(--ink);font-weight:600;}
.save-btn{position:absolute;right:var(--pad);top:var(--pad);background:var(--ink);color:var(--paper);border:none;padding:10px 20px;font-size:12px;font-weight:600;font-family:inherit;letter-spacing:.04em;cursor:pointer;}
.save-btn:hover{background:#333;}
@media (max-width:600px){.save-btn{position:static;display:block;margin-top:12px;width:100%;}}

/* ── Section ── */
.section{margin-bottom:44px;}
.section-head{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:20px;}
.section-head .idx{font-size:13px;font-weight:700;color:var(--accent);letter-spacing:.04em;}
.section-head h2{font-size:21px;font-weight:700;letter-spacing:-.01em;}
.section-download-btn{width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;align-self:center;padding:0;border:0;border-radius:4px;background:transparent;color:var(--ink-3);cursor:pointer;}
.section-download-btn:hover{background:#f1f1f1;color:var(--ink);}
.section-download-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
.section-download-btn:disabled{cursor:wait;}
.section-download-btn svg{width:16px;height:16px;display:block;}
.section-head .note{margin-left:auto;font-size:12px;color:var(--ink-3);letter-spacing:.02em;}
.section.section-export-mode{max-width:none!important;background:#fff;}
.section.section-export-mode .section-head{flex-wrap:nowrap;gap:14px;}
.section.section-export-mode .section-head h2{font-size:21px;}
.section.section-export-mode .section-head .note{width:auto;margin-left:auto;font-size:12px;}
.section.section-export-mode .table-scroll{overflow:visible!important;}
.section.section-export-mode table{width:100%;font-size:13px;}
.section.section-export-mode thead th{padding:12px 16px;font-size:11px;}
.section.section-export-mode tbody td{padding:11px 16px;}
.section.section-export-mode .chart-grid-2{grid-template-columns:1fr 1fr;}
.section.section-export-mode .chart-card{padding:24px;}
.report-timestamp{text-align:center;color:#b5b5b5;font-size:10px;letter-spacing:.04em;margin-top:8px;padding-top:12px;}

/* ── Data strip (overview) ── */
.strip{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--rule);}
.cell{padding:22px 24px;border-right:1px solid var(--rule);}
.cell:last-child{border-right:none;}
.cell .num{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;}
.cell .val{font-size:34px;font-weight:800;letter-spacing:-.02em;margin-top:12px;font-variant-numeric:tabular-nums;line-height:1;}
.cell .sub{font-size:12px;color:var(--ink-2);margin-top:8px;letter-spacing:.02em;}

/* ── Chart card ── */
.chart-card{border:1px solid var(--rule);padding:24px;}
.chart-card .chart-title{font-size:16px;font-weight:700;letter-spacing:-.01em;}
.chart-card .chart-desc{font-size:12px;color:var(--ink-3);margin:6px 0 14px;letter-spacing:.02em;}
.chart-canvas-wrap{position:relative;height:440px;}
.chart-grid-2{display:grid;grid-template-columns:1fr 1fr;gap:24px;}
.timeline-card{border:1px solid var(--rule);background:#fbfbf8;overflow-x:auto;overflow-y:hidden;}
.timeline-card svg{display:block;width:100%;height:auto;min-width:900px;}
.timeline-empty{padding:32px;color:var(--ink-3);font-size:13px;}

/* ── Stats grid ── */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--rule);border-bottom:none;}
.stat{padding:16px 18px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule);}
.stat:nth-child(4n){border-right:none;}
.stat .l{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:600;}
.stat .v{font-size:20px;font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;}

/* ── Table ── */
.table-box{border:1px solid var(--rule);padding:0;}
.table-scroll{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:13px;}
thead th{text-align:right;padding:12px 20px;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2);border-bottom:2px solid var(--rule-strong);font-weight:600;white-space:nowrap;}
thead th:first-child,tbody td:first-child{text-align:left;}
thead th:nth-child(2),tbody td.name{text-align:left;}
tbody td{padding:11px 16px;border-bottom:1px solid var(--rule);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
tbody tr:hover{background:#fafafa;}
td.name{font-weight:500;text-align:left;}
tbody tr.summary-row{font-weight:600;background:#fafafa;}
tbody tr.summary-row td{border-top:2px solid var(--rule-strong);}

/* ── Notice ── */
.notice{border-left:3px solid var(--accent);background:#fafafa;padding:12px 16px;font-size:13px;color:var(--ink-2);letter-spacing:.02em;margin-bottom:36px;}

/* ── P&L Calendar ── */
.cal-toggles{display:flex;gap:0;margin-left:auto;}
.cal-btn{background:transparent;border:1px solid var(--rule);padding:4px 14px;font-size:12px;font-family:inherit;cursor:pointer;color:var(--ink-2);}
.cal-btn:first-child{border-right:none;}
.cal-btn:last-child{border-left:none;}
.cal-btn.active{background:var(--ink);color:var(--paper);border-color:var(--ink);}
.cal-nav{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:12px;}
.cal-nav-btn{background:transparent;border:1px solid var(--rule);padding:6px 14px;font-size:14px;cursor:pointer;color:var(--ink);}
.cal-nav-btn:hover{background:var(--rule);}
.cal-title{font-size:15px;font-weight:600;min-width:160px;text-align:center;}
.cal-grid{display:grid;gap:3px;}
.cal-grid.day{grid-template-columns:repeat(7,1fr);}
.cal-grid.month{grid-template-columns:repeat(4,1fr);}
.cal-grid.year{grid-template-columns:repeat(4,1fr);}
.cal-cell{aspect-ratio:1;font-size:14px;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:0;cursor:pointer;position:relative;font-variant-numeric:tabular-nums;}
.cal-cell .day-num{font-weight:600;line-height:1;margin-bottom:16px;}
.cal-cell .day-amt{font-size:12px;line-height:1;margin-top:1px;}
.cal-cell .day-pct{font-size:12px;line-height:1;margin-top:6px;}
.cal-cell.no-data{background:#f5f5f5;color:#ccc;cursor:default;}
.cal-cell.weekday{background:transparent;color:var(--ink-3);font-size:10px;font-weight:600;aspect-ratio:auto;height:auto;padding:4px 0;cursor:default;border:none;text-align:center;display:block;}
.cal-legend{display:flex;align-items:center;justify-content:center;gap:4px;margin-top:12px;font-size:10px;color:var(--ink-2);}
.cal-legend-label{margin:0 6px;}
@media (max-width:600px){
  .cal-toggles{width:100%;margin-left:0;margin-top:8px;}
  .cal-grid.day{grid-template-columns:repeat(7,1fr);font-size:9px;}
  .cal-cell .day-amt{font-size:7px;}
  .cal-cell .day-pct{font-size:6px;}
}

@media (max-width:880px){
  .strip{grid-template-columns:repeat(2,1fr);}
  .strip .cell:nth-child(2){border-right:none;}
  .strip .cell:nth-child(1),.strip .cell:nth-child(2){border-bottom:1px solid var(--rule);}
  .chart-grid-2{grid-template-columns:1fr;}
  .stat-grid{grid-template-columns:repeat(2,1fr);}
  .stat:nth-child(2n){border-right:none;}
  .chart-canvas-wrap{height:360px;}
  .masthead h1{font-size:32px;}
}
@media (max-width:600px){
  :root{--pad:16px;}
  body{padding:14px;}
  .masthead{border-bottom-width:2px;padding-bottom:12px;margin-bottom:24px;}
  .masthead .kicker{font-size:10px;letter-spacing:.14em;}
  .masthead h1{font-size:24px;}
  .masthead .meta{font-size:11px;gap:12px;}
  .section{margin-bottom:28px;}
  .section-head{gap:8px;padding-bottom:8px;margin-bottom:14px;flex-wrap:wrap;}
  .section-head h2{font-size:16px;}
  .section-head .note{font-size:10px;margin-left:0;width:100%;}
  /* ai coding: 移动端概览改为每行三列并校正分隔线 2026/08/30: 08:51 */
  .strip{grid-template-columns:repeat(3,minmax(0,1fr));}
  .strip .cell:nth-child(1),.strip .cell:nth-child(2),.strip .cell:nth-child(3){border-bottom:1px solid var(--rule);}
  .strip .cell:nth-child(2){border-right:1px solid var(--rule);}
  .strip .cell:nth-child(3){border-right:none;}
  .cell{min-width:0;padding:9px 4px;}
  .cell .num{font-size:8px;letter-spacing:.04em;}
  .cell .val{font-size:15px;margin-top:6px;white-space:nowrap;}
  .cell .sub{font-size:8px;letter-spacing:0;overflow-wrap:anywhere;}
  .chart-card{padding:14px;}
  .chart-card .chart-title{font-size:14px;}
  /* ai coding: 移动端两个饼图改为并排两列并保持原始比例 2026/08/30: 08:52 */
  .chart-grid-2{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
  .chart-grid-2 .chart-card{padding:10px;}
  /* ai coding: 缩减移动端折线图和持仓收益排行高度 2026/08/30: 08:52 */
  .chart-canvas-wrap{height:173px;}
  .chart-canvas-wrap[style*="380px"],.chart-canvas-wrap[style*="340px"]{height:147px!important;}
  .chart-canvas-wrap[style*="height:420px"]{height:280px!important;}
  /* ai coding: 移动端统计摘要改为每行三列并校正分隔线 2026/08/30: 08:51 */
  .stat-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
  .stat:nth-child(2n){border-right:1px solid var(--rule);}
  .stat:nth-child(3n){border-right:none;}
  .stat{min-width:0;padding:9px 4px;}
  .stat .v{font-size:13px;white-space:nowrap;}
  .stat .l{font-size:8px;letter-spacing:.04em;}
  table{font-size:11px;}
  thead th{padding:8px 10px;font-size:9px;}
  tbody td{padding:8px 10px;}
  .notice{font-size:11px;padding:10px 12px;}
}
</style>
</head>
<body>

<div id="page">
<div class="masthead">
  <div class="kicker">Portfolio Performance Report</div>
  <h1>持仓收益分析</h1>
  <div class="meta" id="meta"></div>
  <button class="save-btn" onclick="saveAsImage()">SAVE AS PNG</button>
</div>

<!-- ai coding: 精简章节文案并删除全部英文副标题 2026/08/30: 08:53 -->
<!-- 01 Overview -->
<div class="section" data-section="overview">
  <div class="section-head">
    <span class="idx">01</span>
    <h2>概览</h2>
  </div>
  <div class="strip" id="strip"></div>
</div>

<!-- 02 综合走势 -->
<div class="section" data-section="summary">
  <div class="section-head">
    <span class="idx">02</span>
    <h2>资产 · 收益 · 收益率</h2>
  </div>
  <div class="chart-card">
    <div class="chart-canvas-wrap">
      <canvas id="chartMaster"></canvas>
    </div>
  </div>
</div>

<!-- 03 回撤分析 -->
<div class="section" data-section="drawdown">
  <div class="section-head">
    <span class="idx">03</span>
    <h2>回撤分析</h2>
  </div>
  <div class="chart-card">
    <div class="chart-canvas-wrap" style="height:340px;">
      <canvas id="chartDrawdown"></canvas>
    </div>
  </div>
</div>

<!-- 04 仓位率 -->
<div class="section" data-section="position">
  <div class="section-head">
    <span class="idx">04</span>
    <h2>仓位率</h2>
  </div>
  <div class="chart-card">
    <div class="chart-canvas-wrap" style="height:340px;">
      <canvas id="chartPosition"></canvas>
    </div>
  </div>
</div>

<!-- 05 结构分布 -->
<div class="section" data-section="allocation">
  <div class="section-head">
    <span class="idx">05</span>
    <h2>结构分布</h2>
  </div>
  <div class="chart-grid-2">
    <div class="chart-card">
      <div class="chart-title">仓位分布</div>
      <div class="chart-desc">按当前市值占比</div>
      <div class="chart-canvas-wrap" style="aspect-ratio:1.2;height:auto;">
        <canvas id="chartAllocation"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <div class="chart-title">市场分布</div>
      <div class="chart-desc">A股 / 港股 / 美股</div>
      <div class="chart-canvas-wrap" style="aspect-ratio:1.2;height:auto;">
        <canvas id="chartMarket"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- 06 Ranking -->
<div class="section" data-section="ranking">
  <div class="section-head">
    <span class="idx">06</span>
    <h2>持仓收益排行</h2>
  </div>
  <div class="chart-card">
    <div class="chart-title">各标的收益（万）</div>
    <div class="chart-canvas-wrap" style="height:420px;">
      <canvas id="chartRanking"></canvas>
    </div>
  </div>
</div>

<!-- 07 Statistics -->
<div class="section" data-section="stats">
  <div class="section-head">
    <span class="idx">07</span>
    <h2>统计摘要</h2>
  </div>
  <div class="stat-grid" id="statsGrid"></div>
</div>

<!-- 08 Holdings detail -->
<div class="section" data-section="holdings">
  <div class="section-head">
    <span class="idx">08</span>
    <h2>持仓明细</h2>
  </div>
  <div class="table-box">
    <div class="table-scroll">
      <table id="holdingsTable">
        <thead>
          <tr>
            <th>市场</th>
            <th>公司名称</th>
            <th>成本价</th>
            <th>当前价</th>
            <th>数量</th>
            <th>投入</th>
            <th>当前</th>
            <th>收益</th>
            <th>收益率</th>
            <th>仓位</th>
          </tr>
        </thead>
        <tbody id="holdingsBody"></tbody>
      </table>
    </div>
  </div>
</div>
<!-- 09 Timeline -->
<div class="section" data-section="timeline">
  <div class="section-head">
    <span class="idx">09</span>
    <h2>重仓股持有时间线</h2>
    <span class="note">交易记录与显示设置来自 config.json</span>
  </div>
  <div class="timeline-card">__TIMELINE_SVG__</div>
</div>

<!-- 10 P&L Calendar -->
<div class="section" data-section="calendar">
  <div class="section-head">
    <span class="idx">10</span>
    <h2>盈亏日历</h2>
    <div class="cal-toggles">
      <button class="cal-btn active" data-view="day">日</button>
      <button class="cal-btn" data-view="month">月</button>
      <button class="cal-btn" data-view="year">年</button>
    </div>
  </div>
  <div class="cal-nav">
    <button class="cal-nav-btn" id="calPrev">←</button>
    <span class="cal-title" id="calTitle"></span>
    <button class="cal-nav-btn" id="calNext">→</button>
  </div>
  <div class="cal-grid" id="calGrid"></div>
  <div class="cal-legend">
    <span class="cal-legend-label">亏损</span>
    <span class="cal-swatch" style="background:#007a33;width:14px;height:14px;"></span>
    <span class="cal-swatch" style="background:#c5e8d0;width:14px;height:14px;"></span>
    <span class="cal-swatch" style="background:#e4e4e4;width:14px;height:14px;"></span>
    <span class="cal-swatch" style="background:#f5c6cf;width:14px;height:14px;"></span>
    <span class="cal-swatch" style="background:#e4002b;width:14px;height:14px;"></span>
    <span class="cal-legend-label">盈利</span>
  </div>
</div>

<!-- 11 清仓盈亏 -->
<div class="section" data-section="closed">
  <div class="section-head">
    <span class="idx">11</span>
    <h2>清仓盈亏</h2>
    <span class="note">已卖出标的的盈亏</span>
  </div>
  <div class="chart-card">
    <div class="chart-title">清仓标的收益（万）</div>
    <div class="chart-desc">红涨绿跌，按最近一次快照的盈亏估算</div>
    <div class="chart-canvas-wrap" style="min-height:360px;">
      <canvas id="chartClosed"></canvas>
    </div>
  </div>
</div>

<!-- 12 年化收益率 -->
<div class="section" data-section="annual_returns">
  <div class="section-head">
    <span class="idx">12</span>
    <h2>年化收益率</h2>
  </div>
  <div class="chart-card">
    <table class="holdings-table" id="annualReturnsTable">
      <thead>
        <tr>
          <th style="text-align:left">年份</th>
          <th style="text-align:right">累计净值</th>
          <th style="text-align:right">收益率</th>
        </tr>
      </thead>
      <tbody id="annualReturnsBody"></tbody>
      <tfoot id="annualReturnsFoot"></tfoot>
    </table>
  </div>
</div>
<div class="report-timestamp">生成于 __GENERATED_AT__</div>
</div>
<script>
const rawData = __DATA__;
const stats = __STATS__;
const pageConfig = __CONFIG__;

const snapshots = rawData.snapshots || [];
const latest = snapshots[snapshots.length - 1] || {};
const summary = latest.summary || {};
const holdings = latest.holdings || [];

// ── Swiss palette ──
const INK   = '#111111';
const RED   = '#e4002b';
const SLATE = '#6b7280';
const RULE  = '#e4e4e4';
const INK2  = '#5b5b5b';
const INK3  = '#9a9a9a';
const PROFIT = '#e4002b';
const LOSS   = '#007a33';
// 仓位率三档灰阶
const POS_INK = '#374151';
const POS_MID = '#9ca3af';
const POS_LT  = '#d1d5db';

const fmtWan = v => v == null ? '—' : (Math.abs(v/10000) >= 1 ? (v/10000).toLocaleString('zh-CN',{maximumFractionDigits:1}) + '万' : v.toLocaleString('zh-CN',{maximumFractionDigits:0}));
const fmtPct = v => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2) + '%';
const colorClass = v => v == null ? '' : (v > 0 ? 'up' : v < 0 ? 'down' : '');
const FONT = "'Inter','Noto Sans SC',sans-serif";
// ai coding: 根据移动端断点控制 Y 轴标题显隐 2026/08/30: 08:44
const showYAxisTitle = window.innerWidth > 600;
const dateAxisTicks = {
  autoSkip: true,
  maxTicksLimit: window.innerWidth <= 600 ? 4 : 8,
  autoSkipPadding: 16,
  minRotation: 0,
  maxRotation: 0,
  callback(value) {
    const dateLabel = this.getLabelForValue(value);
    return dateLabel ? dateLabel.slice(5).replace('-', '/') : '';
  }
};

// ── Meta ──
document.getElementById('meta').innerHTML =
  snapshots.length > 1
    ? '报告区间 <b>' + snapshots[0].date + ' → ' + latest.date + '</b>'
    : '快照日期 <b>' + (latest.date || '—') + '</b>'
  + '　·　样本 <b>' + snapshots.length + ' 天</b>'
  + '　·　持仓 <b>' + holdings.length + ' 只</b>';

// ── 01 Overview strip ──
const stripEl = document.getElementById('strip');
const holdingsCurrent = summary.regions?.['整体']?.current ?? summary.holdings_current;
const totalPnl = summary.total_pnl;
const totalRoi = summary.total_roi;
const cells = [
  { num:'01 · TOTAL VALUE', label:'总当前值', value: fmtWan(holdingsCurrent), sub:'含现金 · ' + holdings.length + ' 只持仓', cls:'' },
  { num:'02 · P&L', label:'总收益', value: fmtWan(totalPnl), sub:'文档汇总', cls: colorClass(totalPnl) },
  { num:'03 · ROI', label:'总收益率', value: fmtPct(totalRoi), sub:'年初至今', cls: colorClass(totalRoi) },
  { num:'04 · MAX DRAWDOWN', label:'最大回撤', value: stats.max_drawdown != null ? stats.max_drawdown.toFixed(2) + '%' : '—', sub: snapshots.length > 1 ? '峰值至谷值' : '需多日数据', cls:'down' },
];
stripEl.innerHTML = cells.map(c => `
  <div class="cell">
    <div class="num">${c.num}</div>
    <div class="val ${c.cls}">${c.value}</div>
    <div class="sub">${c.label} · ${c.sub}</div>
  </div>`).join('');

// ── Time series ──
const dates = snapshots.map(s => s.date);
const assetValues = snapshots.map(s => (s.summary || {}).holdings_current || 0);
const pnlValues   = snapshots.map(s => (s.summary || {}).total_pnl);
const roiValues   = snapshots.map(s => (s.summary || {}).total_roi);

const assetWan = assetValues.map(v => v ? +(v/10000).toFixed(2) : null);
const pnlWan   = pnlValues.map(v => v != null ? +(v/10000).toFixed(2) : null);
const roiVals  = roiValues.map(v => v != null ? v : null);

// position rate series + region current values
const regionKeys = ['整体', '国内', '境外'];
const posRate = {};
regionKeys.forEach(r => posRate[r] = []);
const regCur = {};
regionKeys.forEach(r => regCur[r] = []);
snapshots.forEach(s => {
  const sg = s.summary || {};
  const b = sg.base;
  const regions = sg.regions || {};
  regionKeys.forEach(r => {
    const reg = regions[r];
    const cur = (reg && reg.current != null) ? reg.current : null;
    const inv = (reg && reg.invested != null) ? reg.invested : null;
    regCur[r].push(cur);
    if (b && b > 0 && inv != null) {
      posRate[r].push(+(inv / b * 100).toFixed(2));
    } else {
      posRate[r].push(null);
    }
  });
});

// drawdown per region (peak-to-current)
function ddSeries(arr){
  let peak = 0;
  return arr.map(v => {
    if (v == null) return null;
    if (v > peak) peak = v;
    return peak > 0 ? Math.round((v - peak) / peak * 100 * 100) / 100 : 0;
  });
}
const ddOverall  = ddSeries(regCur['整体']);
const ddDomestic = ddSeries(regCur['国内']);
const ddOverseas = ddSeries(regCur['境外']);

// ai coding: 平滑折线并配置主图线型与默认显隐状态 2026/08/29: 15:25
const smoothLine = {
  tension: .4,
  cubicInterpolationMode: 'monotone',
  pointRadius: 0,
  pointHoverRadius: 0,
};

// ── 02 Master combined chart (资产/收益/收益率, 双轴) ──
const masterDatasets = [
  { label:'资产走势', data: assetWan, borderColor: INK, borderWidth: 2.5, yAxisID:'yMoney',
    hidden: true, ...smoothLine },
  { label:'收益走势', data: pnlWan, borderColor: RED, borderWidth: 2, borderDash:[6,4], yAxisID:'yMoney',
    hidden: true, ...smoothLine },
  { label:'收益率', data: roiVals, borderColor: RED, borderWidth: 2, yAxisID:'yPerf',
    ...smoothLine },
];

new Chart(document.getElementById('chartMaster'), {
  type: 'line',
  data: { labels: dates, datasets: masterDatasets },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
    plugins: {
      legend: {
        position: 'top',
        onHover: (e) => { e.native.target.style.cursor = 'pointer'; },
        onLeave: (e) => { e.native.target.style.cursor = ''; },
        labels: { usePointStyle: true, pointStyle: 'line', boxWidth: 26, padding: 16,
                  color: INK, font: { size: 12, family: FONT, weight: '500' } }
      },
      tooltip: {
        callbacks: {
          label: ctx => {
            const v = ctx.parsed.y;
            if (v == null) return ctx.dataset.label + ': —';
            if (ctx.dataset.yAxisID === 'yMoney') return ctx.dataset.label + ': ' + fmtWan(v * 10000);
            return ctx.dataset.label + ': ' + v.toFixed(2) + '%';
          }
        }
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { ...dateAxisTicks, color: INK2, font: { size: 11, family: FONT } }
      },
      yMoney: {
        position: 'left',
        // ai coding: 移动端隐藏金额 Y 轴标题 2026/08/30: 08:44
        title: { display: showYAxisTitle, text: '金额 (万)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
        grid: { color: RULE }, border: { color: INK },
        ticks: { color: INK2, font: { size: 11, family: FONT } }
      },
      yPerf: {
        position: 'right',
        // ai coding: 移动端隐藏收益率 Y 轴标题 2026/08/30: 08:44
        title: { display: showYAxisTitle, text: '收益率 (%)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
        grid: { drawOnChartArea: false }, border: { display: false },
        ticks: { color: INK3, font: { size: 11, family: FONT }, callback: v => v + '%' }
      }
    }
  }
});

// ── 03 Drawdown (single filled area) ──
new Chart(document.getElementById('chartDrawdown'), {
  type: 'line',
  data: {
    labels: dates,
    datasets: [
      { label:'回撤', data: ddOverall, borderColor: RED, borderWidth: 2,
        backgroundColor: 'rgba(228,0,43,0.32)', fill: true,
        ...smoothLine },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
    plugins: {
      legend: { position: 'top',
        onHover: (e) => { e.native.target.style.cursor = 'pointer'; },
        onLeave: (e) => { e.native.target.style.cursor = ''; },
        labels: { usePointStyle: true, pointStyle: 'rect', boxWidth: 14, padding: 14, color: INK, font: { size: 12, family: FONT, weight: '500' } } },
      tooltip: { callbacks: { label: ctx => (ctx.parsed.y == null ? '—' : '回撤: ' + ctx.parsed.y.toFixed(2) + '%') } }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { ...dateAxisTicks, color: INK2, font: { size: 11, family: FONT } }
      },
      y: {
        // ai coding: 移动端隐藏回撤 Y 轴标题 2026/08/30: 08:44
        title: { display: showYAxisTitle, text: '回撤 (%)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
        grid: { color: RULE }, border: { color: INK },
        ticks: { color: INK2, font: { size: 11, family: FONT }, callback: v => v + '%' } }
    }
  }
});

// ── 04 Position rate (single curve, from holdings_pos_curr_pct) ──
const posRateData = snapshots.map(s => (s.summary || {}).holdings_pos_curr_pct);
const fullLine = dates.map(() => 100);
new Chart(document.getElementById('chartPosition'), {
  type: 'line',
  data: {
    labels: dates,
    datasets: [
      { label:'仓位', data: posRateData, borderColor: INK, borderWidth: 2.5,
        ...smoothLine },
      { label:'满仓', data: fullLine, borderColor: SLATE, borderWidth: 1.5, borderDash:[6,5],
        ...smoothLine, fill: false },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
    plugins: {
      legend: { position: 'top',
        onHover: (e) => { e.native.target.style.cursor = 'pointer'; },
        onLeave: (e) => { e.native.target.style.cursor = ''; },
        labels: { usePointStyle: true, pointStyle: 'line', boxWidth: 26, padding: 14, color: INK, font: { size: 12, family: FONT, weight: '500' } } },
      tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y == null ? '—' : ctx.parsed.y.toFixed(2) + '%') } }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { ...dateAxisTicks, color: INK2, font: { size: 11, family: FONT } }
      },
      y: { min: 0, suggestedMax: 100,
        // ai coding: 移动端隐藏仓位率 Y 轴标题 2026/08/30: 08:44
        title: { display: showYAxisTitle, text: '仓位率 (%)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
        grid: { color: RULE }, border: { color: INK },
        ticks: { color: INK2, font: { size: 11, family: FONT }, callback: v => v + '%' } }
    }
  }
});

// ── 05 Allocation (doughnut, grayscale + red accent) ──
const allocData = holdings
  .filter(h => h.current != null && h.current > 0)
  .map(h => ({ name: h.name, value: h.current }))
  .sort((a, b) => b.value - a.value);

const GREY_RAMP = ['#3a3a3a','#5b5b5b','#7a7a7a','#9a9a9a','#b5b5b5','#cccccc','#dcdcdc','#e8e8e8'];
const allocColors = allocData.map((d, i) => i === 0 ? RED : GREY_RAMP[(i - 1) % GREY_RAMP.length]);

new Chart(document.getElementById('chartAllocation'), {
  type: 'doughnut',
  data: { labels: allocData.map(d => d.name), datasets: [{ data: allocData.map(d => d.value), backgroundColor: allocColors, borderWidth: 1, borderColor: '#fff' }] },
  options: {
    responsive: true, maintainAspectRatio: true, aspectRatio: 1.2, cutout: '58%',
    onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 10, color: INK, font: { size: 11, family: FONT } } },
      tooltip: { callbacks: { label: ctx => {
        const total = allocData.reduce((s, d) => s + d.value, 0);
        const pct = (ctx.parsed / total * 100).toFixed(1);
        return ctx.label + ': ' + fmtWan(ctx.parsed) + ' (' + pct + '%)';
      } } }
    }
  }
});

// ── 03 Market (doughnut, Swiss-toned) ──
const marketMap = {};
holdings.forEach(h => {
  const m = h.market || '其他';
  if (h.current != null) marketMap[m] = (marketMap[m] || 0) + h.current;
});
const marketLabels = Object.keys(marketMap);
const marketData = marketLabels.map(m => marketMap[m]);
const marketNames = { CN: 'A股', HK: '港股', US: '美股' };
const marketColor = { CN: RED, HK: '#5b5b5b', US: '#9a9a9a', '其他': '#cccccc' };
const marketColors = marketLabels.map(m => marketColor[m] || '#cccccc');

new Chart(document.getElementById('chartMarket'), {
  type: 'doughnut',
  data: { labels: marketLabels.map(m => marketNames[m] || m), datasets: [{ data: marketData, backgroundColor: marketColors, borderWidth: 1, borderColor: '#fff' }] },
  options: {
    responsive: true, maintainAspectRatio: true, aspectRatio: 1.2, cutout: '58%',
    onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 10, color: INK, font: { size: 11, family: FONT } } },
      tooltip: { callbacks: { label: ctx => {
        const total = marketData.reduce((s, v) => s + v, 0);
        const pct = (ctx.parsed / total * 100).toFixed(1);
        return ctx.label + ': ' + fmtWan(ctx.parsed) + ' (' + pct + '%)';
      } } }
    }
  }
});

// ── 04 Ranking (bar, red up / green down) ──
const ranked = holdings.filter(h => h.pnl != null).sort((a, b) => b.pnl - a.pnl);
new Chart(document.getElementById('chartRanking'), {
  type: 'bar',
  data: {
    labels: ranked.map(h => h.name),
    datasets: [{
      label: '收益',
      data: ranked.map(h => h.pnl / 10000),
      backgroundColor: ranked.map(h => h.pnl > 0 ? PROFIT : h.pnl < 0 ? LOSS : '#9a9a9a'),
      borderRadius: 0,
    }]
  },
  options: {
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: ctx => fmtWan(ctx.parsed.x * 10000) + ' (' + fmtPct(ranked[ctx.dataIndex].roi) + ')' } }
    },
    scales: {
      x: { grid: { color: RULE }, border: { color: INK }, ticks: { color: INK2, font: { size: 11, family: FONT }, callback: v => v + '万' } },
      y: { grid: { display: false }, ticks: { color: INK, font: { size: 12, family: FONT } } }
    }
  }
});

// ── 05 Stats grid ──
const statsEl = document.getElementById('statsGrid');
const statItems = [];
statItems.push({ l: '持仓数量', v: stats.holdings_count + ' 只' });
if (stats.max_drawdown != null) statItems.push({ l: '最大回撤', v: stats.max_drawdown.toFixed(2) + '%', cls: 'down' });
if (stats.max_daily_return != null) statItems.push({ l: '最大日收益', v: fmtPct(stats.max_daily_return), cls: colorClass(stats.max_daily_return) });
if (stats.min_daily_return != null) statItems.push({ l: '最大日亏损', v: fmtPct(stats.min_daily_return), cls: colorClass(stats.min_daily_return) });
if (stats.max_roi != null) statItems.push({ l: '最大收益率', v: stats.max_roi_name + ' ' + fmtPct(stats.max_roi), cls: colorClass(stats.max_roi) });
if (stats.min_roi != null) statItems.push({ l: '最小收益率', v: stats.min_roi_name + ' ' + fmtPct(stats.min_roi), cls: colorClass(stats.min_roi) });
if (stats.max_pnl != null) statItems.push({ l: '最大收益额', v: stats.max_pnl_name + ' ' + fmtWan(stats.max_pnl), cls: colorClass(stats.max_pnl) });
if (stats.min_pnl != null) statItems.push({ l: '最大亏损额', v: stats.min_pnl_name + ' ' + fmtWan(stats.min_pnl), cls: colorClass(stats.min_pnl) });
statItems.push({ l: '持仓收益率', v: fmtPct(summary.holdings_roi), cls: colorClass(summary.holdings_roi) });
statItems.push({ l: '持仓收益', v: fmtWan(summary.holdings_pnl), cls: colorClass(summary.holdings_pnl) });

statsEl.innerHTML = statItems.map(s => `
  <div class="stat">
    <div class="l">${s.l}</div>
    <div class="v ${s.cls || ''}">${s.v}</div>
  </div>`).join('');

// ── 06 Holdings table ──
const totalCurrent = holdings.reduce((s, h) => s + (h.current || 0), 0);
const tbody = document.getElementById('holdingsBody');
const sortedHoldings = [...holdings].sort((a, b) => (b.current || 0) - (a.current || 0));
let holdingsHtml = sortedHoldings.map(h => {
  const isNote = h.current_price_raw == null && (h.quantity == null || h.quantity === 0);
  const pct = totalCurrent > 0 && h.current ? (h.current / totalCurrent * 100).toFixed(1) + '%' : '—';
  return `<tr>
    <td>${h.market || '—'}</td>
    <td class="name">${h.name}</td>
    <td>${isNote ? '—' : (h.cost_price_raw || '—')}</td>
    <td>${h.current_price_raw || '—'}</td>
    <td>${h.quantity != null ? h.quantity.toLocaleString() : '—'}</td>
    <td>${fmtWan(h.invested)}</td>
    <td>${fmtWan(h.current)}</td>
    <td class="${colorClass(h.pnl)}">${fmtWan(h.pnl)}</td>
    <td class="${colorClass(h.roi)}">${fmtPct(h.roi)}</td>
    <td>${pct}</td>
  </tr>`;
}).join('');

// Cash row: 现金 = 整体 - 持仓
const overallCur = (summary.regions && summary.regions['\u6574\u4f53'] && summary.regions['\u6574\u4f53'].current) || 0;
const overallInv = (summary.regions && summary.regions['\u6574\u4f53'] && summary.regions['\u6574\u4f53'].invested) || 0;
const cashCurrent = overallCur - totalCurrent;
const cashInvested = cashCurrent;  // 现金不随行情变，投入=当前（与当前一致，避免用文档旧"整体投入"算出1.5万）
holdingsHtml += `<tr class="summary-row">
  <td>—</td>
  <td class="name">现金</td>
  <td>—</td>
  <td>—</td>
  <td>—</td>
  <td>${fmtWan(cashInvested)}</td>
  <td>${fmtWan(cashCurrent)}</td>
  <td>—</td>
  <td>—</td>
  <td>${overallCur !== 0 ? (cashCurrent / overallCur * 100).toFixed(1) + '%' : '—'}</td>
</tr>`;

tbody.innerHTML = holdingsHtml;

// ── 09 P&L Calendar ──
(function(){
  const calGrid = document.getElementById('calGrid');
  const calTitle = document.getElementById('calTitle');
  let view = 'day';
  let cursor = new Date();
  const fmtCal = v => v == null ? '—' : (v/10000).toFixed(1);  // always 万, 1 decimal

  // compute daily stock P&L only when both today and the previous calendar day have snapshots
  const pnlMap = {};
  snapshots.forEach((s, i) => {
    const d = s.date;
    if (i > 0) {
      const prev = snapshots[i-1];
      const dayGap = Math.round((Date.parse(d + 'T00:00:00Z') - Date.parse(prev.date + 'T00:00:00Z')) / 86400000);
      if (dayGap === 1) {
        const cur = (s.summary || {}).holdings_current;
        const prevCur = (prev.summary || {}).holdings_current;
        if (cur != null && prevCur > 0) {
          pnlMap[d] = {
            amt: +(cur - prevCur).toFixed(0),
            pct: +((cur - prevCur) / prevCur * 100).toFixed(2)
          };
        }
      }
    }
  });

  function colorFor(val, max) {
    if (val == null || max === 0) return '#f5f5f5';
    const r = val / max;
    if (r < 0) {
      const t = Math.min(1, Math.abs(r));
      return `rgba(0,122,51,${0.15 + t * 0.85})`;
    }
    if (r > 0) {
      const t = Math.min(1, r);
      return `rgba(228,0,43,${0.15 + t * 0.85})`;
    }
    return '#f5f5f5';
  }

  function renderDay() {
    const y = cursor.getFullYear(), m = cursor.getMonth();
    calTitle.textContent = `${y}年${m+1}月`;
    calGrid.className = 'cal-grid day';
    const DOW = ['一','二','三','四','五','六','日'];
    let html = DOW.map(d => `<div class="cal-cell weekday">${d}</div>`).join('');

    const first = new Date(y,m,1).getDay()||7;
    const days = new Date(y,m+1,0).getDate();
    const today = new Date().toISOString().slice(0,10);
    const vals = []; for(let i=1;i<=days;i++){const dd=`${y}-${String(m+1).padStart(2,'0')}-${String(i).padStart(2,'0')}`;const e=pnlMap[dd];vals.push(e?Math.abs(e.amt):0);}
    const maxV = Math.max(...vals, 1);

    for(let i=1;i<first;i++) html+='<div class="cal-cell no-data"></div>';
    for(let d=1;d<=days;d++){
      const dd = `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const e = pnlMap[dd];
      let bg = '#f5f5f5', darkText = false, cls = ' no-data', textCls = '';
      if (e) {
        const intensity = Math.min(1, Math.abs(e.amt) / maxV);
        darkText = intensity > 0.45;
        if (e.amt > 0) bg = `rgba(228,0,43,${0.12 + intensity * 0.88})`;
        else bg = `rgba(0,122,51,${0.12 + intensity * 0.88})`;
        cls = '';
        textCls = e.amt > 0 ? 'up' : 'down';
      }
      const border = dd === today ? 'border:2px solid #111;' : '';
      const tc = darkText ? 'color:#fff;' : '';
      html += `<div class="cal-cell${cls}" style="background:${bg};${border}${tc}">
        <span class="day-num">${d}</span>
        ${e ? `<span class="day-amt ${textCls}" style="${tc}">${e.amt>0?'+':''}${fmtCal(e.amt)}</span><span class="day-pct ${textCls}" style="${tc}">${e.pct>0?'+':''}${e.pct}%</span>` : ''}
      </div>`;
    }
    calGrid.innerHTML = html;
  }

  function renderMonth() {
    const y = cursor.getFullYear();
    calTitle.textContent = `${y}年`;
    calGrid.className = 'cal-grid month';
    let html = '';
    for(let m=0;m<12;m++){
      let sum=0,maxA=0,totalCurr=0;const days=[];
      for(let d=1;d<=new Date(y,m+1,0).getDate();d++){
        const dd=`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        const e=pnlMap[dd];if(e){sum+=e.amt;days.push(e.amt);maxA=Math.max(maxA,Math.abs(e.amt));}
      }
      // find the snapshot closest to end of month for asset value
      const monthEnd = new Date(y,m+1,0);
      const snap = [...snapshots].reverse().find(s => new Date(s.date) <= monthEnd);
      if(snap) totalCurr = (((snap.summary || {}).regions || {}).整体 || {}).current || 1;
      const roi = totalCurr > 0 && sum ? +(sum / totalCurr * 100).toFixed(2) : null;
      const intensity = maxA ? Math.min(1, Math.abs(sum)/maxA) : 0;
      const dark = intensity > 0.45;
      const tc = dark ? 'color:#fff;' : '';
      const bg = sum===0&&!days.length?'#f5f5f5':(sum>=0?`rgba(228,0,43,${0.12+intensity*0.88})`:`rgba(0,122,51,${0.12+intensity*0.88})`);
      html += `<div class="cal-cell" style="background:${bg};${tc}">
        <span class="day-num">${m+1}月</span>
        ${days.length ? `<span class="day-amt ${sum>0?'up':'down'}" style="${tc}">${fmtCal(sum)}</span><span class="day-pct ${sum>0?'up':'down'}" style="${tc}">${roi?roi.toFixed(1):'—'}%</span>` : '<span class="day-amt">—</span>'}
      </div>`;
    }
    calGrid.innerHTML = html;
  }

  function renderYear() {
    const years = [...new Set(snapshots.map(s=>+s.date.slice(0,4)))].sort();
    calTitle.textContent = '全部年份';
    calGrid.className = 'cal-grid year';
    let html = '';
    years.forEach(y => {
      const yrSnaps = snapshots.filter(s=>s.date.slice(0,4)==String(y));
      const totalPnl = yrSnaps.length>1 ? yrSnaps[yrSnaps.length-1].summary.total_pnl : 0;
      const totalRoi = yrSnaps.length ? yrSnaps[yrSnaps.length-1].summary.total_roi : null;
      const intensity = Math.min(1, Math.abs(totalPnl) / 500000);
      const dark = intensity > 0.3;
      const tc = dark ? 'color:#fff;' : '';
      const bg = totalPnl>=0?`rgba(228,0,43,${0.12+intensity*0.88})`:`rgba(0,122,51,${0.12+intensity*0.88})`;
      html += `<div class="cal-cell" style="background:${bg};${tc}">
        <span class="day-num">${y}</span>
        <span class="day-amt ${totalPnl>0?'up':'down'}" style="${tc}">${fmtCal(totalPnl)}</span>
        <span class="day-pct ${totalPnl>0?'up':'down'}" style="${tc}">${totalRoi!=null?totalRoi.toFixed(1):'—'}%</span>
      </div>`;
    });
    calGrid.innerHTML = html;
  }

  function render(){if(view==='day')renderDay();else if(view==='month')renderMonth();else renderYear();}

  document.getElementById('calPrev').onclick = () => {
    if(view==='day') cursor.setMonth(cursor.getMonth()-1);
    else if(view==='month') cursor.setFullYear(cursor.getFullYear()-1);
    else return;
    render();
  };
  document.getElementById('calNext').onclick = () => {
    if(view==='day') cursor.setMonth(cursor.getMonth()+1);
    else if(view==='month') cursor.setFullYear(cursor.getFullYear()+1);
    else return;
    render();
  };
  document.querySelectorAll('.cal-btn').forEach(b => b.onclick = () => {
    document.querySelector('.cal-btn.active').classList.remove('active');
    b.classList.add('active');
    view = b.dataset.view;
    cursor = new Date();
    render();
  });

  render();
})();

// ── Notice (single day) ──
if (!multiDay) {
  const n = document.createElement('div');
  n.className = 'notice';
  n.textContent = '当前仅 1 天数据：综合图已展示各曲线当前取值，点击图例可单独查看；走势与回撤趋势需多日数据方能显现。每日 15:00 自动快照后逐步积累。';
  document.querySelector('.masthead').after(n);
}
// ── 10 Closed positions ──
(function(){
  const currNames = new Set(holdings.map(h => h.name));
  const closedMap = {};
  snapshots.forEach(snap => {
    snap.holdings.forEach(h => {
      if (currNames.has(h.name)) return;
      if (!closedMap[h.name]) {
        closedMap[h.name] = {
          name: h.name, first: snap.date, last: snap.date,
          first_invested: h.invested || 0, last_current: h.current || 0,
          first_cost: h.cost_price, last_price: h.current_price
        };
      } else {
        closedMap[h.name].last = snap.date;
        if (h.current != null) closedMap[h.name].last_current = h.current;
        if (h.current_price != null) closedMap[h.name].last_price = h.current_price;
      }
    });
  });
  Object.values(closedMap).forEach(c => {
    c.pnl = c.last_current - c.first_invested;
    // 收益率优先用（卖出价-成本价）/成本价，缺失时回退投入口径
    c.roi = (c.first_cost && c.last_price) ? ((c.last_price - c.first_cost) / c.first_cost * 100) : (c.first_invested ? (c.pnl / c.first_invested * 100) : 0);
  });
  const closed = Object.values(closedMap).sort((a,b) => a.pnl - b.pnl);
  if (closed.length === 0) {
    document.getElementById('chartClosed').parentElement.parentElement.parentElement.style.display = 'none';
    return;
  }
  new Chart(document.getElementById('chartClosed'), {
    type: 'bar',
    data: {
      labels: closed.map(c => c.name),
      datasets: [{
        data: closed.map(c => c.pnl / 10000),
        backgroundColor: closed.map(c => c.pnl > 0 ? PROFIT : c.pnl < 0 ? LOSS : '#9a9a9a'),
        borderRadius: 0,
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      onHover: (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => {
          const c = closed[ctx.dataIndex];
          return fmtWan(c.pnl) + ' (' + fmtPct(c.roi) + ')';
        }}}
      },
      scales: {
        x: { grid: { color: RULE }, ticks: { color: INK2, font: { size: 11, family: FONT } } },
        y: { grid: { display: false }, ticks: { color: INK, font: { size: 11, family: FONT } } }
      }
    }
  });
})();

</script>
<script>
async function downloadElementAsPng(element, filename, horizontalPadding = 0, verticalPadding = 0){
  const renderScale = 2;
  const canvas = await html2canvas(element, {
    scale: renderScale,
    useCORS: true,
    backgroundColor: '#ffffff',
    windowWidth: Math.max(document.documentElement.clientWidth, element.scrollWidth)
  });
  let outputCanvas = canvas;
  if (horizontalPadding > 0 || verticalPadding > 0) {
    const horizontalPaddingPx = horizontalPadding * renderScale;
    const verticalPaddingPx = verticalPadding * renderScale;
    outputCanvas = document.createElement('canvas');
    outputCanvas.width = canvas.width + horizontalPaddingPx * 2;
    outputCanvas.height = canvas.height + verticalPaddingPx * 2;
    const context = outputCanvas.getContext('2d');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, outputCanvas.width, outputCanvas.height);
    context.drawImage(canvas, horizontalPaddingPx, verticalPaddingPx);
  }
  const link = document.createElement('a');
  link.download = filename;
  link.href = outputCanvas.toDataURL('image/png');
  link.click();
}

function waitForExportLayout(){
  return new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

function resizeSectionCharts(section){
  if (typeof Chart === 'undefined' || typeof Chart.getChart !== 'function') return;
  section.querySelectorAll('canvas').forEach(canvas => {
    const chart = Chart.getChart(canvas);
    if (chart) chart.resize();
  });
}

async function saveAsImage(){
  const btn = document.querySelector('.save-btn');
  btn.textContent = 'SAVING...';
  btn.disabled = true;
  try {
    await downloadElementAsPng(
      document.getElementById('page'),
      'portfolio_' + (latest.date || 'report') + '.png',
      24,
      48
    );
  } finally {
    btn.textContent = 'SAVE AS PNG';
    btn.disabled = false;
  }
}

document.querySelectorAll('.section-head h2').forEach(title => {
  const downloadButton = document.createElement('button');
  downloadButton.type = 'button';
  downloadButton.className = 'section-download-btn';
  downloadButton.title = '下载此板块图片';
  downloadButton.setAttribute('aria-label', '下载' + title.textContent.trim() + '图片');
  downloadButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 5-5-5M5 21h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  title.insertAdjacentElement('afterend', downloadButton);

  downloadButton.addEventListener('click', async event => {
    event.preventDefault();
    const section = title.closest('.section');
    if (!section || downloadButton.disabled) return;

    const sectionId = section.dataset.section || 'section';
    const originalCursor = document.body.style.cursor;
    const originalWidth = section.style.width;
    const scrollWidths = Array.from(section.querySelectorAll('.table-scroll')).map(el => el.scrollWidth);
    const exportWidth = Math.max(1120, section.scrollWidth, ...scrollWidths);
    downloadButton.disabled = true;
    downloadButton.style.visibility = 'hidden';
    document.body.style.cursor = 'wait';
    section.classList.add('section-export-mode');
    section.style.width = exportWidth + 'px';
    try {
      await waitForExportLayout();
      resizeSectionCharts(section);
      await waitForExportLayout();
      await downloadElementAsPng(
        section,
        'portfolio_' + sectionId + '_' + (latest.date || 'report') + '.png',
        16
      );
    } finally {
      section.classList.remove('section-export-mode');
      section.style.width = originalWidth;
      resizeSectionCharts(section);
      document.body.style.cursor = originalCursor;
      downloadButton.style.visibility = '';
      downloadButton.disabled = false;
    }
  });
});
</script>
<script>
// ── Annual Returns Table ──
(function() {
  const arData = (stats.annual_returns || []);
  if (arData.length === 0) return;
  const tbody = document.getElementById('annualReturnsBody');
  const tfoot = document.getElementById('annualReturnsFoot');
  const theadTr = document.querySelector('#annualReturnsTable thead tr');
  if (!tbody) return;

  const benchmarks = stats.benchmarks || {};
  const benchNames = Object.keys(benchmarks);
  const showBench = benchNames.length > 0;

  // Add benchmark header columns
  if (showBench && theadTr) {
    benchNames.forEach(name => {
      const th = document.createElement('th');
      th.style.textAlign = 'right';
      th.textContent = name;
      theadTr.appendChild(th);
    });
  }

  let nav = 1.0;
  arData.forEach(d => {
    nav *= (1 + d.return / 100);
    const color = d.return >= 0 ? PROFIT : LOSS;
    const yearLabel = d.type === 'current' ? d.year + ' (YTD)' : String(d.year);
    let html = '<td>' + yearLabel + '</td>'
      + '<td style="text-align:right">' + nav.toFixed(4) + '</td>'
      + '<td style="text-align:right;color:' + color + ';font-weight:600;">' + (d.return >= 0 ? '+' : '') + d.return.toFixed(2) + '%</td>';
    if (showBench) {
      benchNames.forEach(name => {
        const bench = benchmarks[name];
        const entry = bench.data.find(b => b.year === d.year);
        if (entry) {
          const c = entry.return >= 0 ? PROFIT : LOSS;
          html += '<td style="text-align:right;color:' + c + ';">' + (entry.return >= 0 ? '+' : '') + entry.return.toFixed(2) + '%</td>';
        } else {
          html += '<td style="text-align:right;">—</td>';
        }
      });
    }
    const tr = document.createElement('tr');
    tr.innerHTML = html;
    tbody.appendChild(tr);
  });
  // CAGR row
  const cagr = stats.annual_cagr;
  if (cagr != null) {
    const color = cagr >= 0 ? PROFIT : LOSS;
    let html = '<td style="font-weight:700;padding:4px 16px;">投资以来年化</td>'
      + '<td style="text-align:right;font-weight:600;padding:8px 16px;">' + (stats.annual_cumulative_nav || 0).toFixed(4) + '</td>'
      + '<td style="text-align:right;padding:8px 16px;color:' + color + ';font-weight:700;">' + (cagr >= 0 ? '+' : '') + cagr.toFixed(2) + '%</td>';
    if (showBench) {
      benchNames.forEach(name => {
        const b = benchmarks[name];
        if (b.cagr != null) {
          const c = b.cagr >= 0 ? PROFIT : LOSS;
          html += '<td style="text-align:right;padding:8px 16px;color:' + c + ';font-weight:700;">' + (b.cagr >= 0 ? '+' : '') + b.cagr.toFixed(2) + '%</td>';
        } else {
          html += '<td style="text-align:right;padding:8px 16px;">—</td>';
        }
      });
    }
    const tr = document.createElement('tr');
    tr.style.borderTop = '2px solid ' + INK;
    tr.innerHTML = html;
    if (tfoot) tfoot.appendChild(tr);
  }
})();
</script>
<script>
// Apply config: order sections exactly as listed, then hide disabled sections.
if (pageConfig && pageConfig.sections) {
  const page = document.getElementById('page');
  const timestamp = page ? page.querySelector('.report-timestamp') : null;
  const allSections = Array.from(document.querySelectorAll('.section[data-section]'));
  const configuredSections = Object.keys(pageConfig.sections)
    .map(id => document.querySelector('[data-section="' + id + '"]'))
    .filter(Boolean);
  const configuredSet = new Set(configuredSections);
  const orderedSections = configuredSections.concat(
    allSections.filter(section => !configuredSet.has(section))
  );

  if (page) {
    orderedSections.forEach(section => page.insertBefore(section, timestamp));
  }

  orderedSections.forEach(section => {
    const id = section.dataset.section;
    if (Object.prototype.hasOwnProperty.call(pageConfig.sections, id)) {
      section.style.display = pageConfig.sections[id] ? '' : 'none';
    }
  });

  let visibleIndex = 1;
  orderedSections.forEach(section => {
    if (section.style.display === 'none') return;
    const index = section.querySelector('.section-head .idx');
    if (index) index.textContent = String(visibleIndex).padStart(2, '0');
    visibleIndex += 1;
  });
}
if (pageConfig && !pageConfig.save_button) {
  const btn = document.querySelector('.save-btn');
  if (btn) btn.style.display = 'none';
}
</script>
</body>
</html>
"""


def generate_report(snapshots, stats):
    """生成 HTML 报告"""
    data_json = json.dumps({"snapshots": snapshots}, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)

    # Load config
    config = {"sections": {}, "save_button": True}
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except:
        pass
    config_json = json.dumps(config, ensure_ascii=False)
    timeline_svg = generate_timeline_svg(config, write_file=True)
    if not timeline_svg:
        timeline_svg = '<div class="timeline-empty">请在 config.json 中配置 timeline.trades。</div>'

    # Calculate annual returns: historical (from config) + current year YTD (no annualization) + overall CAGR
    annual_data = []
    history = config.get("annual_returns_history", {})
    cumulative_nav = 1.0  # 累计净值
    first_year = None
    for year, ret in sorted(history.items()):
        annual_data.append({"year": int(year), "return": round(ret, 2), "type": "history"})
        cumulative_nav *= (1 + ret / 100)
        if first_year is None:
            first_year = int(year)
    latest_snap = snapshots[-1] if snapshots else {}
    latest_summary = latest_snap.get("summary", {})
    total_roi = latest_summary.get("total_roi")
    snap_date = latest_snap.get("date", "")
    if total_roi is not None and snap_date:
        try:
            d = datetime.strptime(snap_date, "%Y-%m-%d")
            annual_data.append({"year": d.year, "return": round(total_roi, 2), "type": "current"})
            cumulative_nav *= (1 + total_roi / 100)
            # CAGR: from first_year Jan 1 to snapshot date
            if first_year is not None:
                from_start = datetime(first_year, 1, 1)
                total_days = (d - from_start).days
                if total_days > 0:
                    years = total_days / 365.0
                    cagr = cumulative_nav ** (1.0 / years) - 1
                    stats["annual_cagr"] = round(cagr * 100, 2)
                    stats["annual_cumulative_nav"] = round(cumulative_nav, 4)
                    stats["annual_years"] = round(years, 2)
        except:
            pass
    stats["annual_returns"] = annual_data

    # Benchmark indices (沪深300, 纳斯达克, etc.)
    benchmarks_cfg = config.get("annual_returns_benchmarks", {})
    if benchmarks_cfg.get("show") and benchmarks_cfg.get("indices"):
        # Try to load 2026 YTD from temp file (fetched by pipeline)
        bench_ytd = {}
        bench_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_benchmarks.json")
        if os.path.exists(bench_path):
            try:
                with open(bench_path, "r", encoding="utf-8") as f:
                    bench_ytd = json.load(f)
            except:
                pass

        benchmark_data = {}
        for name, idx_cfg in benchmarks_cfg["indices"].items():
            idx_history = idx_cfg.get("history", {})
            idx_annual = []
            idx_nav = 1.0
            idx_first_year = None
            for yr, ret in sorted(idx_history.items()):
                idx_annual.append({"year": int(yr), "return": round(ret, 2)})
                idx_nav *= (1 + ret / 100)
                if idx_first_year is None:
                    idx_first_year = int(yr)
            # 2026 YTD (from fetched data)
            ytd = bench_ytd.get(name)
            if ytd is not None:
                idx_annual.append({"year": 2026, "return": round(ytd, 2)})
                idx_nav *= (1 + ytd / 100)
            # CAGR
            idx_cagr = None
            if idx_first_year is not None and snap_date:
                try:
                    d2 = datetime.strptime(snap_date, "%Y-%m-%d")
                    total_days2 = (d2 - datetime(idx_first_year, 1, 1)).days
                    if total_days2 > 0:
                        years2 = total_days2 / 365.0
                        idx_cagr = round((idx_nav ** (1.0 / years2) - 1) * 100, 2)
                except:
                    pass
            benchmark_data[name] = {
                "data": idx_annual,
                "cagr": idx_cagr,
                "cum_nav": round(idx_nav, 4),
            }
        stats["benchmarks"] = benchmark_data

    stats_json = json.dumps(stats, ensure_ascii=False)

    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    html = (HTML_TEMPLATE
            .replace("__DATA__", data_json)
            .replace("__STATS__", stats_json)
            .replace("__CONFIG__", config_json)
            .replace("__TIMELINE_SVG__", timeline_svg)
            .replace("__GENERATED_AT__", generated_at))

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "report.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    return output_file


# ── 主入口 ────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    snap_dir = os.path.join(script_dir, "portfolio_snapshots")

    if not os.path.exists(snap_dir):
        print("Error: portfolio_snapshots/ 目录不存在", file=sys.stderr)
        sys.exit(1)

    snapshots = load_snapshots(snap_dir)
    if not snapshots:
        print("Error: 没有找到快照文件", file=sys.stderr)
        sys.exit(1)

    stats = calculate_stats(snapshots)
    output_file = generate_report(snapshots, stats)

    print(f"[OK] 报告已生成: {output_file}")
    print(f"     快照数量: {len(snapshots)}")
    print(f"     最新日期: {stats.get('latest_date', 'N/A')}")
    print(f"     持仓数量: {stats.get('holdings_count', 0)}")


if __name__ == "__main__":
    main()
