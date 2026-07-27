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
from datetime import datetime


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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>持仓收益分析 — PORTFOLIO</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
body{
  font-family:'Inter','Noto Sans SC',-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;
  color:var(--ink);
  line-height:1.5;
  font-feature-settings:"tnum" 1;
  -webkit-font-smoothing:antialiased;
  padding:var(--pad);
  max-width:1180px;
  margin:0 auto;
}
.up{color:var(--profit);}
.down{color:var(--loss);}

/* ── Masthead ── */
.masthead{border-bottom:3px solid var(--rule-strong);padding-bottom:18px;margin-bottom:36px;}
.masthead .kicker{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);font-weight:700;}
.masthead h1{font-size:42px;font-weight:800;letter-spacing:-.03em;line-height:1.04;margin-top:8px;}
.masthead .meta{margin-top:12px;font-size:13px;color:var(--ink-2);display:flex;gap:24px;flex-wrap:wrap;letter-spacing:.02em;}
.masthead .meta b{color:var(--ink);font-weight:600;}

/* ── Section ── */
.section{margin-bottom:44px;}
.section-head{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:20px;}
.section-head .idx{font-size:13px;font-weight:700;color:var(--accent);letter-spacing:.04em;}
.section-head h2{font-size:21px;font-weight:700;letter-spacing:-.01em;}
.section-head .note{margin-left:auto;font-size:12px;color:var(--ink-3);letter-spacing:.02em;}

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

/* ── Stats grid ── */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--rule);border-bottom:none;}
.stat{padding:16px 18px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule);}
.stat:nth-child(4n){border-right:none;}
.stat .l{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:600;}
.stat .v{font-size:20px;font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;}

/* ── Table ── */
.table-box{border:1px solid var(--rule);padding:0;}
.table-box .tb-title{font-size:16px;font-weight:700;padding:18px 20px 14px;border-bottom:1px solid var(--rule);letter-spacing:-.01em;}
.table-scroll{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:13px;}
thead th{text-align:right;padding:12px 16px;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2);border-bottom:2px solid var(--rule-strong);font-weight:600;white-space:nowrap;}
thead th:first-child,tbody td:first-child{text-align:left;}
thead th:nth-child(2),tbody td.name{text-align:left;}
tbody td{padding:11px 16px;border-bottom:1px solid var(--rule);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
tbody tr:hover{background:#fafafa;}
td.name{font-weight:500;text-align:left;}

/* ── Notice ── */
.notice{border-left:3px solid var(--accent);background:#fafafa;padding:12px 16px;font-size:13px;color:var(--ink-2);letter-spacing:.02em;margin-bottom:36px;}

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
</style>
</head>
<body>

<div class="masthead">
  <div class="kicker">Portfolio Performance Report</div>
  <h1>持仓收益分析</h1>
  <div class="meta" id="meta"></div>
</div>

<!-- 01 Overview -->
<div class="section">
  <div class="section-head">
    <span class="idx">01</span>
    <h2>概览 / OVERVIEW</h2>
    <span class="note">数值取自文档汇总</span>
  </div>
  <div class="strip" id="strip"></div>
</div>

<!-- 02 综合走势 -->
<div class="section">
  <div class="section-head">
    <span class="idx">02</span>
    <h2>资产 · 收益 · 收益率</h2>
    <span class="note">点击图例可显隐对应曲线</span>
  </div>
  <div class="chart-card">
    <div class="chart-title">综合走势（双轴）</div>
    <div class="chart-desc">左轴：金额（万） ｜ 右轴：收益率（%）</div>
    <div class="chart-canvas-wrap">
      <canvas id="chartMaster"></canvas>
    </div>
  </div>
</div>

<!-- 03 回撤分析 -->
<div class="section">
  <div class="section-head">
    <span class="idx">03</span>
    <h2>回撤分析 / DRAWDOWN</h2>
    <span class="note">资产总值峰值回撤</span>
  </div>
  <div class="chart-card">
    <div class="chart-title">回撤走势（峰值至当前）</div>
    <div class="chart-desc">红色填充为从峰值的回落幅度</div>
    <div class="chart-canvas-wrap" style="height:340px;">
      <canvas id="chartDrawdown"></canvas>
    </div>
  </div>
</div>

<!-- 04 仓位率 -->
<div class="section">
  <div class="section-head">
    <span class="idx">04</span>
    <h2>仓位率 / POSITION RATE</h2>
    <span class="note">持仓占当前总市值的百分比（文档 holdings_pos_curr_pct）</span>
  </div>
  <div class="chart-card">
    <div class="chart-title">仓位率走势</div>
    <div class="chart-desc">灰色虚线为满仓 100% 参考线</div>
    <div class="chart-canvas-wrap" style="height:340px;">
      <canvas id="chartPosition"></canvas>
    </div>
  </div>
</div>

<!-- 05 结构分布 -->
<div class="section">
  <div class="section-head">
    <span class="idx">05</span>
    <h2>结构分布 / ALLOCATION</h2>
  </div>
  <div class="chart-grid-2">
    <div class="chart-card">
      <div class="chart-title">仓位分布</div>
      <div class="chart-desc">按当前市值占比</div>
      <div class="chart-canvas-wrap" style="height:340px;">
        <canvas id="chartAllocation"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <div class="chart-title">市场分布</div>
      <div class="chart-desc">A股 / 港股 / 美股</div>
      <div class="chart-canvas-wrap" style="height:340px;">
        <canvas id="chartMarket"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- 06 Ranking -->
<div class="section">
  <div class="section-head">
    <span class="idx">06</span>
    <h2>持仓收益排行 / RANKING</h2>
  </div>
  <div class="chart-card">
    <div class="chart-title">各标的收益（万）</div>
    <div class="chart-desc">红涨绿跌</div>
    <div class="chart-canvas-wrap" style="height:420px;">
      <canvas id="chartRanking"></canvas>
    </div>
  </div>
</div>

<!-- 07 Statistics -->
<div class="section">
  <div class="section-head">
    <span class="idx">07</span>
    <h2>统计摘要 / STATISTICS</h2>
  </div>
  <div class="stat-grid" id="statsGrid"></div>
</div>

<!-- 08 Holdings detail -->
<div class="section">
  <div class="section-head">
    <span class="idx">08</span>
    <h2>持仓明细 / HOLDINGS</h2>
  </div>
  <div class="table-box">
    <div class="tb-title">完整持仓（按当前市值降序）</div>
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
            <th>股息</th>
            <th>仓位</th>
          </tr>
        </thead>
        <tbody id="holdingsBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const rawData = __DATA__;
const stats = __STATS__;

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

// ── Meta ──
document.getElementById('meta').innerHTML =
  snapshots.length > 1
    ? '报告区间 <b>' + snapshots[0].date + ' → ' + latest.date + '</b>'
    : '快照日期 <b>' + (latest.date || '—') + '</b>'
  + '　·　样本 <b>' + snapshots.length + ' 天</b>'
  + '　·　持仓 <b>' + holdings.length + ' 只</b>';

// ── 01 Overview strip ──
const stripEl = document.getElementById('strip');
const holdingsCurrent = summary.holdings_current;
const totalPnl = summary.total_pnl;
const totalRoi = summary.total_roi;
const cells = [
  { num:'01 · TOTAL VALUE', label:'总当前值', value: fmtWan(holdingsCurrent), sub: holdings.length + ' 只持仓', cls:'' },
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

const multiDay = snapshots.length > 1;
const pt = multiDay ? 3 : 6;

// ── 02 Master combined chart (资产/收益/收益率, 双轴) ──
const masterDatasets = [
  { label:'资产走势', data: assetWan, borderColor: INK, borderWidth: 2.5, yAxisID:'yMoney',
    tension:.25, pointRadius: pt, pointBackgroundColor: INK, pointHoverRadius: pt+2 },
  { label:'收益走势', data: pnlWan, borderColor: RED, borderWidth: 2, yAxisID:'yMoney',
    tension:.25, pointRadius: pt, pointBackgroundColor: RED, pointHoverRadius: pt+2 },
  { label:'收益率', data: roiVals, borderColor: RED, borderWidth: 2, borderDash:[6,4], yAxisID:'yPerf',
    tension:.25, pointRadius: pt, pointBackgroundColor: RED, pointHoverRadius: pt+2 },
];

new Chart(document.getElementById('chartMaster'), {
  type: 'line',
  data: { labels: dates, datasets: masterDatasets },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
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
      x: { grid: { display: false }, ticks: { color: INK2, font: { size: 11, family: FONT } } },
      yMoney: {
        position: 'left',
        title: { display: true, text: '金额 (万)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
        grid: { color: RULE }, border: { color: INK },
        ticks: { color: INK2, font: { size: 11, family: FONT } }
      },
      yPerf: {
        position: 'right',
        title: { display: true, text: '收益率 (%)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
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
        tension:.2, pointRadius: pt, pointBackgroundColor: RED, pointHoverRadius: pt+2 },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'top',
        onHover: (e) => { e.native.target.style.cursor = 'pointer'; },
        onLeave: (e) => { e.native.target.style.cursor = ''; },
        labels: { usePointStyle: true, pointStyle: 'rect', boxWidth: 14, padding: 14, color: INK, font: { size: 12, family: FONT, weight: '500' } } },
      tooltip: { callbacks: { label: ctx => (ctx.parsed.y == null ? '—' : '回撤: ' + ctx.parsed.y.toFixed(2) + '%') } }
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: INK2, font: { size: 11, family: FONT } } },
      y: {
        title: { display: true, text: '回撤 (%)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
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
      { label:'仓位率', data: posRateData, borderColor: INK, borderWidth: 2.5,
        tension:.25, pointRadius: pt, pointBackgroundColor: INK, pointHoverRadius: pt+2 },
      { label:'满仓 100%', data: fullLine, borderColor: SLATE, borderWidth: 1.5, borderDash:[6,5],
        pointRadius: 0, fill: false },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'top',
        onHover: (e) => { e.native.target.style.cursor = 'pointer'; },
        onLeave: (e) => { e.native.target.style.cursor = ''; },
        labels: { usePointStyle: true, pointStyle: 'line', boxWidth: 26, padding: 14, color: INK, font: { size: 12, family: FONT, weight: '500' } } },
      tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y == null ? '—' : ctx.parsed.y.toFixed(2) + '%') } }
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: INK2, font: { size: 11, family: FONT } } },
      y: { min: 0, suggestedMax: 100,
        title: { display: true, text: '仓位率 (%)', color: INK2, font: { size: 11, family: FONT, weight: '600' } },
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
    responsive: true, maintainAspectRatio: false, cutout: '58%',
    plugins: {
      legend: { position: 'right', labels: { boxWidth: 10, color: INK, font: { size: 11, family: FONT } } },
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
    responsive: true, maintainAspectRatio: false, cutout: '58%',
    plugins: {
      legend: { position: 'right', labels: { boxWidth: 10, color: INK, font: { size: 11, family: FONT } } },
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
tbody.innerHTML = sortedHoldings.map(h => {
  const pct = totalCurrent > 0 && h.current ? (h.current / totalCurrent * 100).toFixed(1) + '%' : '—';
  return `<tr>
    <td>${h.market || '—'}</td>
    <td class="name">${h.name}</td>
    <td>${h.cost_price_raw || '—'}</td>
    <td>${h.current_price_raw || '—'}</td>
    <td>${h.quantity != null ? h.quantity.toLocaleString() : '—'}</td>
    <td>${fmtWan(h.invested)}</td>
    <td>${fmtWan(h.current)}</td>
    <td class="${colorClass(h.pnl)}">${fmtWan(h.pnl)}</td>
    <td class="${colorClass(h.roi)}">${fmtPct(h.roi)}</td>
    <td>${fmtWan(h.dividends)}</td>
    <td>${pct}</td>
  </tr>`;
}).join('');

// ── Notice (single day) ──
if (!multiDay) {
  const n = document.createElement('div');
  n.className = 'notice';
  n.textContent = '当前仅 1 天数据：综合图已展示各曲线当前取值，点击图例可单独查看；走势与回撤趋势需多日数据方能显现。每日 15:00 自动快照后逐步积累。';
  document.querySelector('.masthead').after(n);
}
</script>
</body>
</html>
"""


def generate_report(snapshots, stats):
    """生成 HTML 报告"""
    data_json = json.dumps({"snapshots": snapshots}, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__DATA__", data_json).replace("__STATS__", stats_json)

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
