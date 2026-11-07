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
# ai coding: 校验归并快照的资产数值排除无效值 2026/11/07: 13:19
import math
from datetime import datetime, timedelta, timezone

# ai coding: 报告使用配置驱动的原生 HTML 持仓时间线 2026/11/06: 18:24
from generate_timeline import generate_timeline_html


# ── 数据处理 ──────────────────────────────────────────────

# ai coding: 数据入口按交易日归并周末至周五保留抓取日期时间并取同日最后有效快照 2026/11/07: 13:19
def normalize_snapshots(snapshots):
    grouped = {}
    for snapshot in snapshots:
        capture_date = snapshot.get("capture_date") or snapshot["date"]
        captured_day = datetime.strptime(capture_date, "%Y-%m-%d").date()
        trade_day = captured_day - timedelta(days=max(0, captured_day.weekday() - 4))
        value = snapshot.get("summary", {}).get("holdings_current")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        timestamp = snapshot.get("snapshot_time")
        try:
            captured_at = datetime.fromisoformat(timestamp) if timestamp else None
        except (ValueError, TypeError):
            captured_at = None
        if captured_at is None:
            captured_at = datetime.combine(captured_day, datetime.min.time(), tzinfo=timezone(timedelta(hours=8)))
        elif captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone(timedelta(hours=8)))
        normalized = dict(snapshot, date=trade_day.isoformat(), trade_date=trade_day.isoformat(), capture_date=capture_date)
        previous = grouped.get(normalized["date"])
        if previous is None or captured_at >= previous[0]:
            grouped[normalized["date"]] = (captured_at, normalized)
    return [grouped[day][1] for day in sorted(grouped)]


def load_snapshots(snap_dir):
    """读取原始快照并统一归并为工作日序列。"""
    files = sorted(glob.glob(os.path.join(snap_dir, "*.json")))
    snapshots = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            snapshots.append(json.load(fp))
    return normalize_snapshots(snapshots)


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
        # 资产曲线统一使用"整体"region的current（与图表中的「资产」系列一致）
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
<title>PORTFOLIO</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<!-- ai coding: 折线图迁移到 ECharts（TradingView 风格十字光标交互），饼图/柱状图仍用 Chart.js 2026/11/06: 14:48 -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<!-- ai coding: 引入标准哈希库用于金额开关密码校验 2026/11/07: 14:10 -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.2.0/crypto-js.min.js"></script>
<style>
:root{
  --paper:#fcfbf8;
  --ink:#111111;
  --ink-2:#5b5b5b;
  --ink-3:#9a9a9a;
  --rule:#e4e4e4;
  --rule-strong:#111111;
  --accent:#e4002b;      /* Swiss red */
  /* ai coding: 所有盈亏文字与图表统一使用深红盈利深绿亏损 2026/11/06: 18:31 */
  --profit:#9f2d36;
  --loss:#236449;
  --pad:28px;
}
*{margin:0;padding:0;box-sizing:border-box;}
html,body{background:var(--paper);}
/* ai coding: 限制页面宽度并裁切横向溢出防止苹果手机整页左右滑动 2026/11/06: 16:41 */
html,body{width:100%;overflow-x:hidden;overscroll-behavior-x:none;}
@supports(overflow:clip){html,body{overflow-x:clip;}}
/* ai coding: 表格和时间线保留内部横向滚动并阻止滚动传递到整页 2026/11/06: 16:41 */
.table-scroll,.timeline-card{overscroll-behavior-x:contain;max-width:100%;}
.chart-card{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;}
body{
  font-family:'Inter','Noto Sans SC',-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;
  color:var(--ink);
  line-height:1.5;
  font-feature-settings:"tnum" 1;
  -webkit-font-smoothing:antialiased;
  padding:var(--pad);
  max-width:780px;
  margin:0 auto;
  touch-action:manipulation;
}
.up{color:var(--profit);}
.down{color:var(--loss);}

/* ── Masthead ── */
/* ai coding: 页眉保留无边框留白并删除已移除的 meta 样式 2026/10/09: 16:03 */
.masthead{padding-bottom:18px;margin-bottom:36px;}
.masthead .kicker{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);font-weight:700;}
.masthead h1{font-size:42px;font-weight:800;letter-spacing:-.03em;line-height:1.04;margin-top:8px;}
.save-btn{border:none;padding:10px 4px;font-size:12px;font-weight:600;font-family:inherit;cursor:pointer;}

/* ── Section ── */
.section{margin-bottom:44px;}
/* ai coding: 移除章节标题下方的装饰分隔线 2026/10/09: 15:56 */
.section-head{display:flex;align-items:baseline;gap:14px;padding-bottom:10px;margin-bottom:20px;}
.section-head .idx{font-size:13px;font-weight:700;color:var(--accent);letter-spacing:.04em;}
.section-head h2{font-size:21px;font-weight:700;letter-spacing:-.01em;}
/* ai coding: 概览右侧目录与金额开关水平排列并在图片导出时隐藏 2026/11/07: 14:10 */
.page-toc{position:relative;margin-left:auto;align-self:center;display:flex;align-items:center;gap:2px;}
/* ai coding: 增加金额可见开关和密码输入窗口默认隐藏金额片段 2026/11/07: 14:10 */
body:not([data-money-visible="true"]) .money-value{display:none!important;}
.money-dialog{margin:auto;padding:20px;border:1px solid var(--rule);border-radius:12px;background:var(--paper);color:var(--ink);width:min(320px,calc(100% - 32px));}
.money-dialog::backdrop{background:rgba(0,0,0,.2);}
.money-dialog form{display:grid;gap:12px;}
.money-dialog label{font-size:14px;}
.money-dialog input{width:100%;font:inherit;font-size:16px;padding:10px;border:1px solid var(--rule);border-radius:6px;}
.money-dialog button{font:inherit;padding:10px;border:0;border-radius:6px;background:var(--ink);color:var(--paper);}
/* ai coding: 密码窗口操作按钮改为右下角取消与确定 2026/11/07: 14:20 */
.money-dialog-actions{display:flex;justify-content:flex-end;gap:8px;}
.money-dialog-actions button{padding:9px 18px;min-height:44px;}
.money-dialog-actions button[type="button"]{background:transparent;color:var(--ink-2);}
.page-toc-toggle{display:flex;align-items:center;justify-content:center;width:36px;height:36px;background:transparent;border:0;color:var(--ink-2);cursor:pointer;border-radius:6px;}
.page-toc-toggle svg{width:20px;height:20px;}
.page-toc-toggle:hover{background:#f5f5f3;}
.page-toc-list{position:absolute;right:0;top:calc(100% + 8px);z-index:20;width:220px;max-width:calc(100vw - 64px);padding:6px;background:#fff;border:1px solid var(--rule);border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.08);}
.page-toc-list a{display:block;padding:9px 12px;color:var(--ink);font-size:13px;text-decoration:none;border-radius:5px;}
.page-toc-list a:hover,.page-toc-list a:focus-visible{background:#f5f5f3;}
.section-export-mode .page-toc{display:none;}
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
/* ai coding: 时间线导出展开完整横向区域并取消固定姓名避免截断截图 2026/11/07: 13:57 */
.section.section-export-mode .ht-scroll{overflow:visible!important;}
.section.section-export-mode .ht-name{position:static;}
.section:is([data-section="holdings"],[data-section="timeline"]) .section-head h2{touch-action:manipulation;user-select:none;-webkit-user-select:none;}
.section.section-export-mode table{width:100%;font-size:13px;}
.section.section-export-mode thead th{padding:12px 16px;font-size:11px;}
.section.section-export-mode tbody td{padding:11px 16px;}
.section.section-export-mode .chart-grid-2{grid-template-columns:1fr 1fr;}
.section.section-export-mode .chart-card{padding:24px;}
/* ai coding: 顶部保留更新时间和无边框起止日期输入并隐藏空提示 2026/10/09: 16:03 */
/* ai coding: 更新时间放在页面内容之外顶部居中平时折叠仅下拉时展开 2026/11/06: 18:46 */
.report-timestamp{position:relative;top:calc(-1 * var(--pad));height:0;overflow:hidden;opacity:0;text-align:center;color:var(--ink-3);font-size:11px;letter-spacing:.04em;display:flex;align-items:center;justify-content:center;transition:height .18s ease,opacity .18s ease;}
.report-timestamp.is-pulling{transition:none;}
@media(prefers-reduced-motion:reduce){.report-timestamp{transition:none;}}
.date-filter{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:18px;font-size:12px;color:var(--ink-2);}
.date-filter label{display:flex;align-items:center;gap:6px;}
.date-filter input{font:inherit;border:0;border-radius:4px;padding:7px 10px;background:#f5f5f5;color:var(--ink);min-width:0;}
.date-filter input:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
.date-filter-status{width:100%;color:var(--loss);}
.date-filter-status:empty{display:none;}

/* ── Data strip (overview) ── */
/* ai coding: 移除概览卡片外框和单元格分隔线 2026/10/09: 15:56 */
.strip{display:grid;grid-template-columns:repeat(4,1fr);}
.cell{padding:22px 24px;}
.cell .num{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;}
.cell .val{font-size:34px;font-weight:800;letter-spacing:-.02em;margin-top:12px;font-variant-numeric:tabular-nums;line-height:1;}
.cell .sub{font-size:12px;color:var(--ink-2);margin-top:8px;letter-spacing:.02em;}

/* ── Chart card ── */
/* ai coding: 仅移除图表容器边框而不修改图表内部线条 2026/10/09: 15:56 */
.chart-card{padding:24px;}
/* ai coding: 非饼图容器铺满内容区宽度并移除左右内边距，保留饼图和表格原布局 2026/10/09: 16:08 */
.section[data-section="summary"] > .chart-card,
.section[data-section="drawdown"] > .chart-card,
.section[data-section="position"] > .chart-card,
.section[data-section="ranking"] > .chart-card,
.section[data-section="closed"] > .chart-card{width:100%;padding-left:0;padding-right:0;}
.chart-card .chart-title{font-size:16px;font-weight:700;letter-spacing:-.01em;}
.chart-card .chart-desc{font-size:12px;color:var(--ink-3);margin:6px 0 14px;letter-spacing:.02em;}
.chart-canvas-wrap{position:relative;height:440px;}
/* ai coding: 资产收益收益率图表高度提高为原来的一点五倍 2026/11/06: 15:46 */
.section[data-section="summary"] .chart-canvas-wrap{height:660px;}
/* ai coding: 折线图容器保留竖向滚动，横向拖动留给 ECharts 十字光标连续刷选 2026/11/06: 14:48 */
#chartMaster,#chartDrawdown,#chartPosition{touch-action:pan-y;}
.chart-grid-2{display:grid;grid-template-columns:1fr 1fr;gap:24px;}
/* ai coding: 时间线与全局盈亏颜色共享变量保留单行端点数字和底部信息 2026/11/06: 18:31 */
.timeline-card{background:var(--paper);overflow:visible;}
.holding-timeline{--ht-profit:var(--profit);--ht-loss:var(--loss);--ht-neutral:#656565;}
/* ai coding: 固定年度轨道宽度仅时间线内部横向滚动并保持标的名称可见 2026/11/06: 19:51 */
.ht-scroll{width:100%;overflow-x:auto;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;}
.ht-canvas{width:calc(var(--ht-time-width) + 126px);}
.ht-scroll .ht-name{position:sticky;left:0;margin-bottom: 5px;z-index:2;background:var(--paper);}
.ht-scroll .ht-row[aria-pressed="true"] .ht-name{background:#f5f5f3 !important;}
@media(max-width:480px){.ht-canvas{width:calc(var(--ht-time-width) + 110px);}}
.ht-profit{--ht-tone:var(--ht-profit);}
.ht-loss{--ht-tone:var(--ht-loss);}
.ht-neutral{--ht-tone:var(--ht-neutral);}
.ht-asof{color:var(--ink-2);font-size:12px;text-align:right;margin-bottom:16px;}
.ht-axis{position:relative;height:28px;margin-left:106px;margin-right:20px;color:var(--ink-2);font-size:12px;}
.ht-axis span{position:absolute;transform:translateX(-50%);}
.ht-axis span:first-child{transform:none;}
.ht-axis span:last-child{transform:translateX(-100%);}
.ht-row{display:grid;grid-template-columns:74px minmax(0,1fr);gap:12px;align-items:center;width:100%;height:60px;border:0;background:none;padding:0;text-align:left;font:inherit;cursor:pointer;}
.ht-row[aria-pressed="true"]{background:#f5f5f3;}
.ht-name{font-size:13px;font-weight:500;color:var(--ink);white-space:nowrap;}
.ht-track{position:relative;height:56px;margin:0 20px;}
.ht-line{position:absolute;left:var(--ht-start);width:var(--ht-span);height:2px;top:37px;background:var(--ht-tone);}
.ht-line::before,.ht-line::after{content:"";position:absolute;top:-3px;width:8px;height:8px;border-radius:50%;background:var(--ht-tone);}
.ht-line::before{left:0;}
.ht-line::after{right:0;}
.ht-line.ht-open::after{background:var(--paper);outline:1px solid var(--ht-tone);}
.ht-annual{position:absolute;left:calc(var(--ht-start) + var(--ht-span));top:14px;transform:translateX(-50%);color:var(--ht-tone);font-size:13px;font-weight:500;white-space:nowrap;font-variant-numeric:tabular-nums;}
.ht-detail{margin-top:18px;padding-top:18px;border-top:1px solid var(--rule);min-height:120px;}
.ht-detail-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums;}
.ht-detail-head b{font-weight:500;font-size:18px;color:var(--ink);}
.ht-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px;}
.ht-metric span{display:block;font-size:12px;color:var(--ink-2);}
.ht-metric strong{display:block;font-weight:500;font-size:20px;margin-top:5px;color:var(--ink);font-variant-numeric:tabular-nums;}
.ht-metric strong.ht-profit,.ht-metric strong.ht-loss{color:var(--ht-tone);}
.ht-status{grid-column:2/-1;align-self:center;font-size:13px;color:var(--ink-2);}
@media(max-width:480px){.ht-row{grid-template-columns:62px minmax(0,1fr);gap:8px;padding: 0 10px;}.ht-axis{margin-left:90px;}.ht-name,.ht-annual{font-size:12px;}.ht-metric strong{font-size:18px;}.ht-detail-head{font-size:11px;}}
.timeline-empty{padding:32px;color:var(--ink-3);font-size:13px;}

/* ── Stats grid ── */
/* ai coding: 移除统计摘要外框和网格分隔线 2026/10/09: 15:56 */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);}
.stat{padding:16px 18px;}
.stat .l{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);font-weight:600;}
.stat .v{font-size:20px;font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;}

/* ── Table ── */
/* ai coding: 恢复原表格容器的浅灰细外框 2026/10/09: 16:07 */
.table-box{border:1px solid var(--rule);padding:0;}
.table-scroll{overflow-x:auto;}
/* ai coding: 恢复原表格布局并移除单元格竖向网格线 2026/10/09: 16:07 */
table{width:100%;border-collapse:collapse;font-size:13px;}
/* ai coding: 恢复表头下方原有的两像素深色横线 2026/10/09: 16:07 */
thead th{text-align:center;padding:12px 20px;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2);border-bottom:2px solid var(--rule-strong);font-weight:600;white-space:nowrap;}
thead th:first-child,tbody td:first-child{text-align:left;}
thead th:nth-child(2),tbody td.name{text-align:left;}
/* ai coding: 恢复数据行之间原有的浅灰细横线 2026/10/09: 16:07 */
tbody td{padding:11px 16px;border-bottom:1px solid var(--rule);text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap;}
tbody tr:hover{background:#fafafa;}
td.name{font-weight:500;text-align:left;}
tbody tr.summary-row{font-weight:600;background:#fafafa;}
/* ai coding: 恢复现金合计行上方原有的深色横线 2026/10/09: 16:07 */
tbody tr.summary-row td{border-top:2px solid var(--rule-strong);}
/* ai coding: 持仓明细容器和表格铺满可用宽度移除外框仅保留表头合计细线 2026/11/06: 18:30 */
.section[data-section="holdings"] .table-box{border:0;width:100%;padding:0;}
.section[data-section="holdings"] .table-scroll{width:100%;}
#holdingsTable{width:100%;}
#holdingsTable thead th{border-bottom:1px solid var(--rule);}
#holdingsTable tbody td{border:0;}
#holdingsTable tbody tr.summary-row td{border-top:1px solid var(--rule);}
/* ai coding: 年化收益率表格沿用持仓明细的细线风格仅保留表头与汇总分隔 2026/11/06: 18:27 */
/* ai coding: 年化收益率表头统一十二像素覆盖移动端与导出表头字号 2026/11/06: 19:33 */
#annualReturnsTable thead th{border-bottom:1px solid var(--rule);font-size:12px;}
#annualReturnsTable tbody td{border:0;}
#annualReturnsTable tfoot td{border-top:1px solid var(--rule);}
/* ai coding: 年化表格所有单元格禁止换行手机使用自动列宽并在表格内部横向滚动 2026/11/06: 20:01 */
.section[data-section="annual_returns"] > .chart-card{width:100%;padding-left:0;padding-right:0;}
#annualReturnsTable{width:100%;}
#annualReturnsTable th,#annualReturnsTable td{white-space:nowrap!important;overflow-wrap:normal;word-break:normal;}
@media(max-width:480px){#annualReturnsTable{table-layout:auto;font-size:12px;}#annualReturnsTable th,#annualReturnsTable td{padding-left:4px;padding-right:4px;}#annualReturnsTable tfoot td{padding-left:4px!important;padding-right:4px!important;}}

/* ── Notice ── */
/* ai coding: 提示信息仅保留浅色背景而不使用左侧边框 2026/10/09: 15:56 */
.notice{background:#fafafa;padding:12px 16px;font-size:13px;color:var(--ink-2);letter-spacing:.02em;margin-bottom:36px;}

/* ai coding: 盈亏日历应用留白细线布局保留日月与金额收益率独立切换 2026/11/06: 17:30 */
.cal-controls{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px;flex-wrap:wrap;}
.cal-toggles{display:flex;gap:4px;}
.cal-btn,.cal-metric-btn{border:0;border-radius:4px;background:transparent;padding:8px 12px;font-size:12px;font-family:inherit;color:var(--ink-3);cursor:pointer;}
.cal-btn.active,.cal-metric-btn.active{background:#f0f3f1;color:var(--ink);}
.cal-nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;}
.cal-nav-btn{background:transparent;border:0;width:40px;height:40px;padding:0;font-size:20px;color:var(--ink-3);cursor:pointer;}
.cal-title{font-size:18px;font-weight:500;}
/* ai coding: 日历日视图改为周一至周五五列月视图保持原布局 2026/11/06: 19:49 */
.cal-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0;}
.cal-grid.month{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;}
.cal-cell{height:62px;min-width:0;padding:9px 2px;display:flex;flex-direction:column;align-items:center;justify-content:space-between;background:transparent;border:0;border-top:1px solid #edf0ee;color:var(--ink);font-family:inherit;box-sizing:border-box;}
.cal-cell[data-date]{cursor:pointer;}
.cal-cell:disabled{color:#9aa3a5;cursor:default;}
.cal-cell .day-num{font-size:12px;font-weight:400;}
.cal-cell .day-value{font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap;}
.cal-cell[aria-pressed="true"]{outline:1px solid var(--ink);outline-offset:-1px;border-radius:3px;}
.cal-cell.weekday{border:0;height:auto;padding:0 0 12px;font-size:11px;color:var(--ink-3);display:block;text-align:center;}
.cal-grid.month .cal-cell{height:88px;padding:16px 8px;}
.cal-grid.month .day-num,.cal-grid.month .day-value{font-size:14px;}
/* ai coding: 日期详情同时展示完整整数盈亏金额和两位小数收益率 2026/11/06: 17:30 */
.cal-detail{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:16px;border-top:1px solid #edf0ee;font-size:12px;}
.cal-detail-date{color:var(--ink-3);}
.cal-detail-values{display:flex;gap:18px;font-variant-numeric:tabular-nums;white-space:nowrap;}
@media(max-width:600px){
  .cal-controls{gap:8px;}
  .cal-btn,.cal-metric-btn{padding:10px 9px;min-height:44px;}
  .cal-nav-btn{width:44px;height:44px;}
  .cal-cell{height:60px;}
  .cal-cell .day-value{font-size:11px;}
  .cal-grid.month .cal-cell{height:84px;}
  .cal-grid.month .day-value{font-size:13px;}
  .cal-detail-values{gap:12px;}
}

@media (max-width:880px){
  .strip{grid-template-columns:repeat(2,1fr);}
  .chart-grid-2{grid-template-columns:1fr;}
  .stat-grid{grid-template-columns:repeat(2,1fr);}
  .chart-canvas-wrap{height:360px;}
/* ai coding: 资产收益收益率图表高度提高为原来的一点五倍 2026/11/06: 15:46 */
.section[data-section="summary"] .chart-canvas-wrap{height:540px;}
  .masthead h1{font-size:32px;}
}
@media (max-width:600px){
  :root{--pad:10px;}
  body{padding:3px;}
  /* ai coding: 移动端页眉保持无边框布局 2026/10/09: 15:56 */
  .masthead{padding-bottom:12px;margin-bottom:24px;}
  .masthead .kicker{font-size:10px;letter-spacing:.14em;}
  .masthead h1{font-size:24px;}
  /* ai coding: 移动端模块间距统一并收紧标题与图表留白 2026/11/06: 15:44 */
  .section{margin-bottom:24px;}
  .section-head{gap:8px;padding-bottom:8px;margin-bottom:4px;flex-wrap:wrap;}
  .section-head h2{font-size:16px;}
  .section-head .note{font-size:10px;margin-left:0;width:100%;}
  /* ai coding: 移动端概览保留三列并移除全部分隔线 2026/10/09: 15:56 */
  .strip{grid-template-columns:repeat(3,minmax(0,1fr));}
  .cell{min-width:0;padding:9px 4px;}
  .cell .num{font-size:8px;letter-spacing:.04em;}
  .cell .val{font-size:15px;margin-top:6px;white-space:nowrap;}
  .cell .sub{font-size:8px;letter-spacing:0;overflow-wrap:anywhere;}
  .chart-card{padding:14px;}
  .chart-card .chart-title{font-size:14px;}
  /* ai coding: 移动端两个饼图改为并排两列并保持原始比例 2026/08/30: 08:52 */
  .chart-grid-2{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
  .chart-grid-2 .chart-card{padding:10px;}
  /* ai coding: 折线图增加读数区后保持足够绘图区高度 2026/11/06: 15:44 */
  .chart-canvas-wrap{height:270px;}
/* ai coding: 资产收益收益率图表高度提高为原来的一点五倍 2026/11/06: 15:46 */
.section[data-section="summary"] .chart-canvas-wrap{height:405px;}
  .chart-canvas-wrap[style*="380px"],.chart-canvas-wrap[style*="340px"]{height:147px!important;}
  .chart-canvas-wrap[style*="height:420px"]{height:280px!important;}
  /* ai coding: 移动端统计摘要保留三列并移除全部分隔线 2026/10/09: 15:56 */
  .stat-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
  .stat{min-width:0;padding:9px 4px;}
  .stat .v{font-size:13px;white-space:nowrap;}
  .stat .l{font-size:8px;letter-spacing:.04em;}
  table{font-size:11px;}
  thead th{padding:8px;font-size:9px;text-align:center;}
  tbody td{padding:8px;text-align:center;}
  /* ai coding: 移动折线图取消负边距由组件配置统一控制左右间距 2026/11/06: 19:02 */
  .section[data-section="summary"] .chart-card,
  .section[data-section="drawdown"] .chart-card,
  .section[data-section="position"] .chart-card{margin-left:0;margin-right:0;width:100%;padding:8px 0 0;}
  /* ai coding: 持仓明细表公司名称列在移动端横向滚动时吸附固定，覆盖左侧市场列 2026/11/06: 15:17 */
  .table-scroll thead th:nth-child(2){position:sticky;left:0;z-index:2;background:var(--paper);}
  .table-scroll tbody td.name{position:sticky;left:0;z-index:1;background:#fcfbf8}
  .table-scroll tbody tr:hover td.name,.table-scroll tbody tr.summary-row td.name{background:var(--paper);}
  .notice{font-size:11px;padding:10px 12px;}
}
/* ai coding: 三个折线图统一标题读数和绘图区间距各保留十二像素 2026/11/06: 16:40 */
.section:is([data-section="summary"],[data-section="drawdown"],[data-section="position"]) .section-head{padding-bottom:0;margin-bottom:0;}
.section:is([data-section="summary"],[data-section="drawdown"],[data-section="position"]) > .chart-card{padding-top:12px;}

/* ai coding: 页眉日期操作与概览统计改用简约排版并将长标的名称独立成行 2026/11/06: 16:22 */
.masthead{margin-bottom:28px;padding-bottom:0;}
.masthead h1{font-size:34px;font-weight:700;line-height:1.2;margin-top:0;}
/* ai coding: 起止日期与保存图片固定在同一行错误状态单独占下一行 2026/11/06: 16:39 */
.date-filter{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:12px;margin-top:20px;}
.date-filter > label{min-width:0;white-space:nowrap;}
.date-filter-status{grid-column:1/-1;grid-row:2;}
.date-filter .save-btn{grid-column:3;grid-row:1;white-space:nowrap;}
.date-filter label{gap:8px;font-size:12px;color:var(--ink-3);}
.date-filter input{padding:8px 10px;border-radius:6px;background:#f6f6f6;font-size:13px;}
.save-btn{background:transparent;color:var(--ink-2);padding:8px 0;margin-left:auto;font-size:12px;}
.strip,.stat-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:24px 20px;}
.cell,.stat{min-width:0;padding:0;}
.cell .num,.stat .l{font-size:11px;font-weight:400;letter-spacing:0;color:var(--ink-3);}
.cell .val{font-size:28px;line-height:1.2;margin-top:8px;font-weight:650;}
.stat .v{font-size:21px;line-height:1.3;margin-top:8px;font-weight:600;white-space:normal;overflow-wrap:anywhere;}
.stat .n{font-size:12px;color:var(--ink-2);line-height:1.5;margin-top:5px;overflow-wrap:anywhere;}
@media(max-width:600px){
  .masthead h1{font-size:28px;}
  /* ai coding: 手机端日期标签输入和导出按钮紧凑单行排列避免窄屏换行 2026/11/06: 16:39 */
  .date-filter{gap:6px;margin-top:16px;}
  .date-filter label{display:flex;flex-direction:row;align-items:center;gap:3px;font-size:10px;}
  .date-filter input{flex:1;width:0;min-width:0;box-sizing:border-box;min-height:36px;padding:6px 4px;font-size:10px;}
  .date-filter input::-webkit-calendar-picker-indicator{width:12px;margin:0;padding:0;}
  .save-btn{justify-self:end;margin-left:0;padding:8px 0;font-size:10px;}
  .strip,.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:22px 24px;}
  .cell .val{font-size:26px;}
  .cell .num,.stat .l{font-size:11px;letter-spacing:0;}
  .stat .v{font-size:20px;}
  .section[data-section="overview"],.section[data-section="stats"]{margin-bottom:32px;}
  .section[data-section="overview"] .section-head,.section[data-section="stats"] .section-head{margin-bottom:18px;}
}

/* ai coding: 日期控件缩窄并用固定格式文本覆盖系统本地化日期显示 2026/11/06: 16:42 */
.date-filter{grid-template-columns:max-content max-content auto;}
.date-input-shell{position:relative;display:inline-flex;align-items:center;justify-content:center;width:108px;height:36px;background:#f6f6f6;border-radius:6px;flex:none;font-size:12px;font-variant-numeric:tabular-nums;}
.date-filter .date-input-shell input{position:absolute;inset:0;width:100%;height:100%;opacity:0;padding:0;cursor:pointer;}
.date-input-shell:focus-within{outline:2px solid var(--accent);outline-offset:2px;}
.date-filter .save-btn{justify-self:start;margin-left:0;}
@media(max-width:600px){.date-input-shell{width:86px;font-size:10px;}}

/* ai coding: 市场分组比例条和标的列表响应手机尺寸并支持选中关联色段 2026/11/06: 17:09 */

#portfolioAllocation{--ink:light-dark(#202a2d,#e8eff1);--muted:light-dark(#7e898d,#a1afb6);background:var(--paper);color:var(--ink);padding:12px 0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;box-sizing:border-box;}
#portfolioAllocation .heading{display:flex;align-items:baseline;gap:12px;margin-bottom:30px;}#portfolioAllocation .heading span{color:light-dark(#d7494f,#ec888e);font-size:13px;}#portfolioAllocation h2{font-size:20px;font-weight:500;margin:0;}
#portfolioAllocation .market-labels,#portfolioAllocation .bar{display:flex;gap:5px;}#portfolioAllocation .market-label{min-width:0;font-size:12px;line-height:1.5;margin-bottom:10px;}#portfolioAllocation .market-label span{display:block;color:var(--muted);font-variant-numeric:tabular-nums;}
#portfolioAllocation .bar{height:32px;margin-bottom:28px;}#portfolioAllocation .market-segments{display:flex;min-width:0;}#portfolioAllocation .segment{min-width:0;box-sizing:border-box;border-right:1px solid var(--paper);transition:opacity .18s;}#portfolioAllocation .segment:last-child{border-right:0;}#portfolioAllocation .segment.active{box-shadow:inset 0 0 0 2px var(--ink);}#portfolioAllocation .segment.dim{opacity:.4;}
#portfolioAllocation .legend{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 36px;}#portfolioAllocation .market-list{display:grid;align-content:start;gap:2px;}#portfolioAllocation .entry{width:100%;display:grid;grid-template-columns:8px minmax(0,1fr) 54px;align-items:center;gap:10px;min-height:44px;padding:4px 0;background:transparent;border:0;text-align:left;font:12px -apple-system,BlinkMacSystemFont,sans-serif;color:var(--ink);box-sizing:border-box;}#portfolioAllocation .swatch{width:8px;height:8px;border-radius:1px;}#portfolioAllocation .name{line-height:1.5;overflow-wrap:anywhere;}#portfolioAllocation .pct{text-align:right;font-variant-numeric:tabular-nums;}#portfolioAllocation .entry[aria-pressed=true] .name{text-decoration:underline;text-underline-offset:5px;}#portfolioAllocation .market-list-head{font-size:11px;color:var(--muted);margin-bottom:6px;}
@media(max-width:460px){#portfolioAllocation{padding:8px 0;}#portfolioAllocation .heading{margin-bottom:24px;}#portfolioAllocation .bar{height:28px;}#portfolioAllocation .legend{grid-template-columns:minmax(0,1fr);gap:20px;}#portfolioAllocation h2{font-size:18px;}}
@media(prefers-reduced-motion:reduce){#portfolioAllocation .segment{transition:none;}}

/* ai coding: 增加白底柔影和暖灰卡片主题且横向不加内边距避免重复组件边距 2026/11/06: 19:16 */
#page[data-theme="soft_shadow"],#page[data-theme="warm_gray"]{--module-fill:#fff;--module-border:#eeeeec;--module-shadow:0 3px 14px rgba(30,35,30,.055);}
#page[data-theme="warm_gray"]{--module-fill:#fcfbf8;--module-border:#e6e1d8;--module-shadow:none;}
#page:is([data-theme="soft_shadow"],[data-theme="warm_gray"]) > .section{background:var(--module-fill);border:1px solid var(--module-border);border-radius:12px;box-shadow:var(--module-shadow);padding:20px 0;margin-bottom:20px;min-width:0;}
#page:is([data-theme="soft_shadow"],[data-theme="warm_gray"]) > .section > .section-head{margin-left:18px;margin-right:18px;}
#page:is([data-theme="soft_shadow"],[data-theme="warm_gray"]) .chart-card{background:transparent;}
@media(max-width:480px){
  #page:is([data-theme="soft_shadow"],[data-theme="warm_gray"]) > .section{padding-top:18px;padding-bottom:18px;}
  #page:is([data-theme="soft_shadow"],[data-theme="warm_gray"]) > .section > .section-head{margin-left:12px;margin-right:12px;}
}
</style>
</head>
<body>
<!-- ai coding: 金额解锁密码窗口右下角提供取消与确定按钮 2026/11/07: 14:20 -->
<dialog class="money-dialog" id="moneyDialog"><form id="moneyForm"><label for="moneyPassword">密码</label><input id="moneyPassword" type="password" autocomplete="current-password" required><div class="money-dialog-actions"><button type="button" id="moneyCancel">取消</button><button type="submit">确定</button></div></form></dialog>

<!-- ai coding: 更新时间移出报告主体作为顶部下拉区域 2026/11/06: 18:46 -->
<div class="report-timestamp">最近更新时间：__GENERATED_AT__（北京时间）</div>
<!-- ai coding: 生成时写入主题避免首屏样式切换闪动 2026/11/06: 19:16 -->
<div id="page" data-theme="__PAGE_THEME__">
<!-- ai coding: 日期栏关闭时同时隐藏空页眉防止二十八像素下边距产生顶部留白 2026/11/06: 19:04 -->
<div class="masthead" __DATE_FILTER_VISIBILITY__>
  <!-- ai coding: 删除页眉重复英文标题只保留报告名称 2026/11/06: 16:22 -->
  <!-- ai coding: 日期选择叠加固定年月日文本保留系统日期选择器 2026/11/06: 16:42 -->
  <!-- ai coding: 日期栏在生成 HTML 时即按配置隐藏避免刷新首帧闪现 2026/11/06: 18:48 -->
  <div class="date-filter" __DATE_FILTER_VISIBILITY__>
    <label>开始 <span class="date-input-shell"><span id="dateStartDisplay" aria-hidden="true"></span><input id="dateStart" type="date" required></span></label>
    <label>结束 <span class="date-input-shell"><span id="dateEndDisplay" aria-hidden="true"></span><input id="dateEnd" type="date" required></span></label>
    <span class="date-filter-status" id="dateFilterStatus" role="status" aria-live="polite"></span>
  <button class="save-btn" onclick="saveAsImage()">保存图片</button>
  </div>
</div>

<!-- ai coding: 精简章节文案并删除全部英文副标题 2026/08/30: 08:53 -->
<!-- 01 Overview -->
<div class="section" data-section="overview">
  <div class="section-head">
    <span class="idx">01</span>
    <h2>概览</h2>
    <!-- ai coding: 概览标题右侧目录图标点击展开当前可见章节 2026/11/06: 20:05 -->
    <div class="page-toc">
      <!-- ai coding: 目录旁金额眼睛开关默认关闭打开需密码验证 2026/11/07: 14:10 -->
      <button type="button" class="page-toc-toggle" id="moneyToggle" aria-label="显示金额" aria-pressed="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path id="moneyEyeSlash" d="m3 3 18 18"/></svg></button>
      <button type="button" class="page-toc-toggle" id="pageTocToggle" aria-label="页面目录" aria-expanded="false" aria-controls="pageTocList"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1"/></svg></button>
      <nav class="page-toc-list" id="pageTocList" aria-label="页面目录" hidden></nav>
    </div>
  </div>
  <div class="strip" id="strip"></div>
</div>

<!-- 02 综合走势 -->
<div class="section" data-section="summary">
  <div class="section-head">
    <span class="idx">02</span>
    <!-- ai coding: 综合折线图标题改为资产与收益走势 2026/11/06: 18:37 -->
    <h2>资产与收益走势</h2>
  </div>
  <div class="chart-card">
    <div class="chart-canvas-wrap">
      <!-- ai coding: 折线图容器由 canvas 换成 div 以承载 ECharts 实例 2026/11/06: 14:48 -->
      <div id="chartMaster" class="echarts-host" style="width:100%;height:100%;"></div>
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
    <div class="chart-canvas-wrap">
      <div id="chartDrawdown" class="echarts-host" style="width:100%;height:100%;"></div>
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
    <div class="chart-canvas-wrap">
      <div id="chartPosition" class="echarts-host" style="width:100%;height:100%;"></div>
    </div>
  </div>
</div>

<!-- 05 结构分布 -->
<div class="section" data-section="allocation">
  <div class="section-head">
    <span class="idx">05</span>
    <h2>结构分布</h2>
  </div>
  <!-- ai coding: 仓位市场圆环合并为单条市场分组比例图与标的列表 2026/11/06: 17:09 -->
  <div id="portfolioAllocation" class="allocation-strip"></div>
</div>

<!-- 06 Ranking -->
<div class="section" data-section="ranking">
  <div class="section-head">
    <span class="idx">06</span>
    <h2>持仓收益排行</h2>
  </div>
    <div class="chart-card">
      <!-- ai coding: 删除收益排行重复说明文字直接展示图表 2026/11/06: 15:55 -->
      <div class="chart-canvas-wrap" style="height:220px;">
        <!-- ai coding: 收益排行容器由 canvas 换成 div 以承载 ECharts 实例 2026/11/06: 15:17 -->
        <div id="chartRanking" class="echarts-host" style="width:100%;height:100%;"></div>
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
    <!-- ai coding: 时间线章节标题简化为时间线目录同步读取新标题 2026/11/06: 20:06 -->
    <h2>时间线</h2>
  </div>
  <!-- ai coding: 在报告中直接渲染 HTML 持仓时间线 2026/11/06: 18:24 -->
  <div class="timeline-card">__TIMELINE_HTML__</div>
</div>

<!-- 10 P&L Calendar -->
<div class="section" data-section="calendar">
  <div class="section-head">
    <span class="idx">10</span>
    <h2>盈亏日历</h2>
  </div>
  <!-- ai coding: 视图和指标分别切换仅保留日月日历并添加双读数日期详情 2026/11/06: 17:30 -->
  <div class="cal-controls">
    <div class="cal-toggles" role="group" aria-label="日月视图">
      <button type="button" class="cal-btn active" data-view="day" aria-pressed="true">日</button>
      <button type="button" class="cal-btn" data-view="month" aria-pressed="false">月</button>
    </div>
    <div class="cal-toggles" role="group" aria-label="盈亏指标">
      <button type="button" class="cal-metric-btn active" data-metric="amt" aria-pressed="true">盈亏金额</button>
      <button type="button" class="cal-metric-btn" data-metric="pct" aria-pressed="false">收益率</button>
    </div>
  </div>
  <div class="cal-nav">
    <button type="button" class="cal-nav-btn" id="calPrev" aria-label="上一期">‹</button>
    <span class="cal-title" id="calTitle"></span>
    <button type="button" class="cal-nav-btn" id="calNext" aria-label="下一期">›</button>
  </div>
  <div class="cal-grid" id="calGrid"></div>
  <div class="cal-detail" id="calDetail" aria-live="polite"></div>
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
    <!-- ai coding: 年化表格增加独立横向滚动容器防止不换行内容撑宽页面 2026/11/06: 20:01 -->
    <div class="table-scroll">
    <table class="holdings-table" id="annualReturnsTable">
      <thead>
        <tr>
          <th style="text-align:left">年份</th>
          <th style="text-align:center">累计净值</th>
          <th style="text-align:center">收益率</th>
        </tr>
      </thead>
      <tbody id="annualReturnsBody"></tbody>
      <tfoot id="annualReturnsFoot"></tfoot>
    </table>
    </div>
  </div>
</div>
</div>
<script>
const rawData = __DATA__;
const stats = __STATS__;
const pageConfig = __CONFIG__;
// ai coding: 金额默认关闭永久授权持久保存开关状态临时授权按上海日期过期 2026/11/07: 14:10
const moneyStorageKey = 'portfolio-money-access-v1';
const moneyDay = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
let moneyAccess = {};
try { moneyAccess = JSON.parse(localStorage.getItem(moneyStorageKey) || '{}') || {}; } catch {}
// ai coding: URL参数与密码输入复用校验有效key在首次渲染前直接解锁并保存授权 2026/11/07: 14:23
function verifyMoneyKey(key) {
  if (typeof key !== 'string' || typeof CryptoJS === 'undefined') return null;
  if (CryptoJS.SHA256(key).toString() === 'd8716d587c9be371a239ec5191a5b5b9cc04ef962d68601465ff304d3e8b9839') return { kind: 'permanent', visible: true };
  const day = moneyDay();
  if (key.trim().toLowerCase() === CryptoJS.MD5(day.replaceAll('-', '.') + 'Z').toString()) return { kind: 'daily', date: day, visible: true };
  return null;
}
const urlMoneyAccess = verifyMoneyKey(new URLSearchParams(location.search).get('key'));
if (urlMoneyAccess) {
  moneyAccess = moneyAccess.kind === 'permanent' ? { kind: 'permanent', visible: true } : urlMoneyAccess;
  try { localStorage.setItem(moneyStorageKey, JSON.stringify(moneyAccess)); } catch {}
}
const validMoneyAccess = () => moneyAccess.kind === 'permanent' || (moneyAccess.kind === 'daily' && moneyAccess.date === moneyDay());
let moneyVisible = validMoneyAccess() && moneyAccess.visible === true;
document.body.dataset.moneyVisible = String(moneyVisible);
const moneyToggle = document.getElementById('moneyToggle');
function saveMoneyAccess() { try { localStorage.setItem(moneyStorageKey, JSON.stringify(moneyAccess)); } catch {} }
function syncMoneyToggle() {
  document.body.dataset.moneyVisible = String(moneyVisible);
  moneyToggle.setAttribute('aria-pressed', String(moneyVisible));
  moneyToggle.setAttribute('aria-label', moneyVisible ? '隐藏金额' : '显示金额');
  document.getElementById('moneyEyeSlash').style.display = moneyVisible ? 'none' : '';
}
function changeMoneyVisibility(visible) {
  moneyVisible = visible;
  moneyAccess.visible = visible;
  saveMoneyAccess(); syncMoneyToggle();
  applyDateRange();
  document.dispatchEvent(new Event('moneyvisibilitychange'));
}
syncMoneyToggle();
document.dispatchEvent(new Event('moneyvisibilitychange'));
// ai coding: 永久密码持久授权每日密码按上海日期加Z的完整三十二位MD5仅授权当天 2026/11/07: 14:16
const moneyDialog = document.getElementById('moneyDialog');
const moneyPassword = document.getElementById('moneyPassword');
moneyToggle.addEventListener('click', () => {
  if (moneyVisible) { changeMoneyVisibility(false); return; }
  if (validMoneyAccess()) { changeMoneyVisibility(true); return; }
  moneyPassword.value = ''; moneyPassword.setCustomValidity('');
  moneyDialog.showModal(); moneyPassword.focus();
});
moneyPassword.addEventListener('input', () => moneyPassword.setCustomValidity(''));
// ai coding: 取消关闭密码窗口并清空输入不改变金额可见状态 2026/11/07: 14:20
document.getElementById('moneyCancel').addEventListener('click', () => {
  moneyDialog.close(); moneyPassword.value = ''; moneyPassword.setCustomValidity(''); moneyToggle.focus();
});
// ai coding: 密码窗口使用与URL相同校验规则避免两种入口授权口径不同 2026/11/07: 14:23
document.getElementById('moneyForm').addEventListener('submit', event => {
  event.preventDefault();
  if (typeof CryptoJS === 'undefined') { moneyPassword.setCustomValidity('校验服务未加载，请刷新页面'); moneyPassword.reportValidity(); return; }
  const access = verifyMoneyKey(moneyPassword.value);
  if (!access) { moneyPassword.setCustomValidity('密码不正确'); moneyPassword.reportValidity(); return; }
  moneyAccess = access;
  moneyDialog.close(); moneyPassword.value = ''; changeMoneyVisibility(true);
});
// ai coding: 上海零点定时失效临时授权后台恢复时复核永久授权保持有效 2026/11/07: 14:15
function expireMoneyAccess() {
  if (moneyAccess.kind === 'daily' && moneyAccess.date !== moneyDay()) {
    moneyAccess = {}; changeMoneyVisibility(false);
  }
}
function scheduleMoneyExpiry() {
  const nextMidnight = Date.parse(moneyDay() + 'T00:00:00+08:00') + 86400000;
  setTimeout(() => { expireMoneyAccess(); scheduleMoneyExpiry(); }, Math.max(1, nextMidnight - Date.now()));
}
scheduleMoneyExpiry();
document.addEventListener('visibilitychange', () => { if (!document.hidden) expireMoneyAccess(); });
window.addEventListener('focus', expireMoneyAccess);
// ai coding: 目录按当前可见模块顺序生成链接支持跳转外部点击和Escape关闭 2026/11/06: 20:05
const pageTocToggle = document.getElementById('pageTocToggle');
const pageTocList = document.getElementById('pageTocList');
function closePageToc() {
  pageTocList.hidden = true;
  pageTocToggle.setAttribute('aria-expanded', 'false');
}
pageTocToggle.addEventListener('click', () => {
  if (!pageTocList.hidden) { closePageToc(); return; }
  pageTocList.replaceChildren();
  document.querySelectorAll('#page > .section[data-section]').forEach(section => {
    const title = section.querySelector('.section-head h2');
    if (!title || !section.getClientRects().length) return;
    if (!section.id) section.id = 'section-' + section.dataset.section;
    const link = document.createElement('a');
    link.href = '#' + section.id;
    link.textContent = title.textContent.trim();
    link.addEventListener('click', event => {
      event.preventDefault();
      closePageToc();
      section.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    });
    pageTocList.appendChild(link);
  });
  pageTocList.hidden = false;
  pageTocToggle.setAttribute('aria-expanded', 'true');
});
document.addEventListener('click', event => {
  if (!event.target.closest('.page-toc')) closePageToc();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !pageTocList.hidden) { closePageToc(); pageTocToggle.focus(); }
});
// ai coding: 按配置归一化模块内外边距比例无效值回退四比六并保留标题独立间距 2026/11/06: 19:19
const componentMargin = name => {
  const value = pageConfig.component_margins?.[name];
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;
};
const componentInnerRatio = (() => {
  const { inner, outer } = pageConfig.component_margin_ratio || {};
  if (![inner, outer].every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0) || Math.max(inner, outer) === 0) return 0.4;
  const scale = Math.max(inner, outer);
  return (inner / scale) / (inner / scale + outer / scale);
})();
function applyComponentMargin(section) {
  const name = section.dataset.section;
  const margin = componentMargin(name);
  const innerMargin = margin * componentInnerRatio;
  const outerMargin = margin * (1 - componentInnerRatio);
  section.style.marginInline = outerMargin + 'px';
  section.style.width = 'calc(100% - ' + outerMargin * 2 + 'px)';
  Array.from(section.children).forEach(content => {
    if (content.classList.contains('section-head') || content.tagName === 'SCRIPT') return;
    content.style.marginInline = innerMargin + 'px';
    content.style.width = 'calc(100% - ' + innerMargin * 2 + 'px)';
  });
}
document.querySelectorAll('.section[data-section]').forEach(applyComponentMargin);
// ai coding: 动态新增清仓组件也只调整内容边距保持标题对齐 2026/11/06: 18:59
new MutationObserver(records => {
  records.forEach(record => record.addedNodes.forEach(node => {
    if (node.nodeType === 1 && node.matches('.section[data-section]')) applyComponentMargin(node);
  }));
}).observe(document.getElementById('page'), { childList: true });
[['date_filter', '.date-filter'], ['report_timestamp', '.report-timestamp']].forEach(([name, selector]) => {
  const element = document.querySelector(selector);
  if (!element) return;
  const margin = componentMargin(name);
  element.style.marginInline = margin + 'px';
  element.style.width = 'calc(100% - ' + margin * 2 + 'px)';
});
// ai coding: 仅在页面顶部单指下拉时展示更新时间松手收起并避开图表及表单手势 2026/11/06: 18:46
const reportTimestamp = document.querySelector('.report-timestamp');
let timestampPull = null;
const closeTimestamp = () => {
  timestampPull = null;
  reportTimestamp.classList.remove('is-pulling');
  reportTimestamp.style.height = '0px';
  reportTimestamp.style.opacity = '0';
};
document.addEventListener('touchstart', event => {
  if (event.touches.length !== 1 || window.scrollY > 0 || event.target.closest('.chart-card,.table-scroll,input,button')) return;
  timestampPull = { x: event.touches[0].clientX, y: event.touches[0].clientY };
}, { passive: true });
document.addEventListener('touchmove', event => {
  if (!timestampPull) return;
  if (event.touches.length !== 1 || window.scrollY > 0) { closeTimestamp(); return; }
  const dx = Math.abs(event.touches[0].clientX - timestampPull.x);
  const dy = event.touches[0].clientY - timestampPull.y;
  if (dy <= 0 || dx > dy) { closeTimestamp(); return; }
  const height = Math.min(52, dy * 0.4);
  reportTimestamp.classList.add('is-pulling');
  reportTimestamp.style.height = height + 'px';
  reportTimestamp.style.opacity = String(Math.min(1, height / 26));
}, { passive: true });
document.addEventListener('touchend', closeTimestamp, { passive: true });
document.addEventListener('touchcancel', closeTimestamp, { passive: true });
// ai coding: 日期栏与页眉同步按配置隐藏避免空容器边距残留默认保持显示 2026/11/06: 19:04
const dateFilterElement = document.querySelector('.date-filter');
if (dateFilterElement) {
  const display = pageConfig.date_filter === false ? 'none' : '';
  dateFilterElement.style.display = display;
  const masthead = dateFilterElement.closest('.masthead');
  if (masthead) masthead.style.display = display;
}

// ai coding: 保留所有快照供日期筛选并共享当前区间末日供图片导出 2026/10/09: 15:56
const allSnapshots = rawData.snapshots || [];
let latest = allSnapshots[allSnapshots.length - 1] || {};

// ── Swiss palette ──
const INK   = '#111111';
const RED   = '#e4002b';
const RULE  = '#e4e4e4';
const INK2  = '#5b5b5b';
const INK3  = '#9a9a9a';
// ai coding: 图表盈亏颜色读取页面全局变量避免各图使用不同红绿色 2026/11/06: 18:31
const PROFIT = getComputedStyle(document.documentElement).getPropertyValue('--profit').trim();
const LOSS = getComputedStyle(document.documentElement).getPropertyValue('--loss').trim();
// 仓位率三档灰阶
const POS_INK = '#374151';
const POS_MID = '#9ca3af';
const POS_LT  = '#d1d5db';

// ai coding: 金额关闭时所有通用金额格式化输出遮罩百分比格式保持可见 2026/11/07: 14:10
const fmtWan = v => !moneyVisible ? '—' : v == null ? '—' : (Math.abs(v/10000) >= 1 ? (v/10000).toLocaleString('zh-CN',{maximumFractionDigits:1}) + '万' : v.toLocaleString('zh-CN',{maximumFractionDigits:0}));
const fmtPct = v => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2) + '%';
const colorClass = v => v == null ? '' : (v > 0 ? 'up' : v < 0 ? 'down' : '');
const FONT = "'Inter','Noto Sans SC',sans-serif";
// ai coding: 移动端断点控制 Y 轴刻度数字显隐与折线线宽；Y 轴标题三端统一去掉（刻度带 % 后缀足以区分，且标题与图例互相遮挡） 2026/11/06: 15:26
const isMobileView = window.innerWidth <= 600;
const hideYAxisLabel = isMobileView;
// ai coding: 资产收益收益率分别固定使用页面石墨灰深红深绿不随正负变色 2026/11/06: 19:23
const C_ASSET = INK2;
const C_PNL = PROFIT;
const C_ROI = LOSS;
// ai coding: 三张折线图全部沿用仓位率的线宽手机一点三桌面二像素 2026/11/06: 18:43
const LW_MAIN = isMobileView ? 1.3 : 2;
// ai coding: 日期刻度改由 ECharts axisLabel.hideOverlap 自动抽稀，原 Chart.js ticks 配置移除 2026/11/06: 14:48

// ai coding: 按所选快照重新计算持仓极值、最大回撤和日收益统计 2026/10/09: 15:58
function calculateRangeStats(snapshots){
  const current = snapshots[snapshots.length - 1] || {};
  const currentHoldings = current.holdings || [];
  const result = { holdings_count: currentHoldings.length };
  ['roi', 'pnl'].forEach(metric => {
    const values = currentHoldings.filter(holding => holding[metric] != null);
    if (!values.length) return;
    const highest = values.reduce((best, holding) => holding[metric] > best[metric] ? holding : best);
    const lowest = values.reduce((worst, holding) => holding[metric] < worst[metric] ? holding : worst);
    result['max_' + metric] = highest[metric];
    result['max_' + metric + '_name'] = highest.name;
    result['min_' + metric] = lowest[metric];
    result['min_' + metric + '_name'] = lowest.name;
  });
  if (snapshots.length > 1) {
    const values = snapshots.map(snapshot => snapshot.summary?.regions?.['整体']?.current || 0);
    let peak = 0;
    result.max_drawdown = 0;
    const dailyReturns = [];
    values.forEach((value, index) => {
      peak = Math.max(peak, value);
      if (peak > 0) result.max_drawdown = Math.min(result.max_drawdown, (value - peak) / peak * 100);
      if (index > 0 && values[index - 1] > 0) dailyReturns.push((value - values[index - 1]) / values[index - 1] * 100);
    });
    if (dailyReturns.length) {
      result.max_daily_return = Math.max(...dailyReturns);
      result.min_daily_return = Math.min(...dailyReturns);
    }
  }
  return result;
}

// ai coding: 折线图迁移到 ECharts（TradingView 风格）：十字吸附光标、读数固定左上角不随手指/鼠标飘移、触屏按住滑动全程跟踪（touch 隐式捕获，移出绘图区不丢定位）、轻点钉住数值 2026/11/06: 14:48
const TV_SPLIT = '#f0f0f0';
const tvAxisLabel = { color: INK3, fontSize: 10, fontFamily: FONT };
function tvTooltip(fmtVal) {
  return {
    trigger: 'axis',
    // 轻点钉住读数、按住拖动连续刷选；position 固定左上角，不再做左右侧切换
    // ai coding: 移动端禁用自动光标改为长按手动显示读数 2026/11/06: 16:31
    triggerOn: isMobileView ? 'none' : 'mousemove|click',
    // ai coding: 固定读数增加左右内边距并限制在图表宽度内 2026/11/06: 15:44
    position: [2, 0],
    confine: true,
    backgroundColor: 'transparent',
    borderWidth: 0,
    padding: 0,
    textStyle: { color: INK, fontSize: 11, fontFamily: FONT },
    extraCssText: 'box-shadow:none;pointer-events:none;',
    axisPointer: {
      // ai coding: 移动端竖线仅响应长按派发的图表动作 2026/11/06: 16:31
      triggerOn: isMobileView ? 'none' : 'mousemove|click',
      type: isMobileView ? 'line' : 'cross',
      snap: true,
      // ai coding: 移动端隐藏横向光标数值避免贴边裁切 2026/11/06: 15:44
      label: { show: !isMobileView, backgroundColor: INK, color: '#fff', fontSize: 10, fontFamily: FONT, padding: [3, 5], borderRadius: 2 },
      lineStyle: { color: INK3, width: 1, type: 'dashed' },
      crossStyle: { color: INK3, width: 1, type: 'dashed' }
    },
    formatter(params) {
      // ai coding: 读数只包含数据曲线不包含底层网格系列 2026/11/06: 16:47
      const items = params.filter(p => p.value != null && p.seriesType !== 'custom');
      if (!items.length) return '';
      // ai coding: 日期和全部系列读数保持一行并按手机宽度缩小字号与间隔 2026/11/06: 15:51
      const width = document.getElementById('chartMaster').clientWidth - 32;
      const fontSize = isMobileView ? Math.max(8, Math.min(11, width / 40)) : 11;
      const date = '<span style="color:' + INK3 + '">' + items[0].axisValue + '</span>';
      const vals = items.map(p => '<span style="display:inline-flex;align-items:center;gap:3px;white-space:nowrap">' + p.marker + p.seriesName + ' <b>' + fmtVal(p) + '</b></span>').join('');
      return '<div style="display:flex;align-items:center;flex-wrap:nowrap;gap:' + (isMobileView ? 6 : 12) + 'px;white-space:nowrap;font-size:' + fontSize + 'px;line-height:18px">' + date + vals + '</div>';
    }
  };
}
// ai coding: 仅Android触屏设备使用原生震动接口轻震八毫秒移除无效iOS隐藏开关方案 2026/11/06: 19:59
const scrubHaptic = (() => {
  const ua = navigator.userAgent || '';
  const isAndroid = /Android/i.test(ua);
  const coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  return () => {
    if (!isAndroid || !coarse || typeof navigator.vibrate !== 'function') return;
    try {
      navigator.vibrate(8);
    } catch (err) { /* 不支持触感反馈的设备静默忽略 */ }
  };
})();
// ai coding: 单指拖动平移图表长按三百五十毫秒进入读数模式松手隐藏光标 2026/11/06: 16:31
document.querySelectorAll('#chartMaster,#chartDrawdown,#chartPosition').forEach(host => {
  let gesture = null;
  let holdTimer = null;
  const chart = () => echarts.getInstanceByDom(host);
  const cancelTimer = () => { clearTimeout(holdTimer); holdTimer = null; };
  // ai coding: 长按滑出绘图区时将读数坐标限制在左右边界滑回后继续跟随 2026/11/06: 16:33
  const showReading = touch => {
    const instance = chart();
    if (!instance) return;
    const bounds = host.getBoundingClientRect();
    const plot = instance.getModel().getComponent('grid').coordinateSystem.getRect();
    const x = Math.max(plot.x + 0.5, Math.min(plot.x + plot.width - 0.5, touch.clientX - bounds.left));
    const y = Math.max(plot.y + 0.5, Math.min(plot.y + plot.height - 0.5, touch.clientY - bounds.top));
    instance.dispatchAction({ type: 'showTip', x, y });
  };
  const release = () => {
    cancelTimer();
    if (gesture?.holding) chart()?.setOption({ dataZoom: [{ moveOnMouseMove: true }] });
    chart()?.dispatchAction({ type: 'hideTip' });
    chart()?.dispatchAction({ type: 'updateAxisPointer', currTrigger: 'leave' });
    gesture = null;
  };
  host.addEventListener('touchstart', event => {
    release();
    if (event.touches.length !== 1) return;
    const touch = event.touches[0];
    gesture = { x: touch.clientX, y: touch.clientY, direction: null, holding: false };
    holdTimer = setTimeout(() => {
      if (!gesture || gesture.direction) return;
      gesture.holding = true;
      chart()?.setOption({ dataZoom: [{ moveOnMouseMove: false }] });
      showReading(touch);
      scrubHaptic();
    }, 350);
  }, { passive: true });
  host.addEventListener('touchmove', event => {
    if (event.touches.length === 2) {
      release();
      if (event.cancelable) event.preventDefault();
      return;
    }
    if (!gesture || event.touches.length !== 1) return;
    const touch = event.touches[0];
    if (gesture.holding) {
      if (event.cancelable) event.preventDefault();
      showReading(touch);
      return;
    }
    const dx = Math.abs(touch.clientX - gesture.x);
    const dy = Math.abs(touch.clientY - gesture.y);
    if (!gesture.direction && Math.max(dx, dy) >= 6) {
      cancelTimer();
      gesture.direction = dx > dy ? 'horizontal' : 'vertical';
    }
    if (gesture.direction === 'horizontal' && event.cancelable) event.preventDefault();
  }, { passive: false });
  host.addEventListener('touchend', release, { passive: true });
  host.addEventListener('touchcancel', release, { passive: true });
});
// ai coding: 从轴指针事件的系列索引读取日期点仅跨日期时触发反馈并在离开时重置 2026/11/06: 19:39
function bindScrubHaptic(chart) {
  let lastIdx = null;
  chart.on('updateAxisPointer', e => {
    const point = e.axesInfo?.find(axis => axis.seriesDataIndices?.length)?.seriesDataIndices[0];
    const idx = e.dataIndex ?? e.dataIndexInside ?? point?.dataIndex ?? point?.dataIndexInside;
    if (idx == null || idx === lastIdx) return;
    if (lastIdx != null) scrubHaptic();
    lastIdx = idx;
  });
  chart.on('hideTip', () => { lastIdx = null; });
}
// ai coding: 极值标签保持错位排布收益类标签与圆点按正负显示全局盈亏色 2026/11/06: 18:31
function tvExtremum(color, unit, lane, values, signed = false) {
  const pointColor = value => signed ? (value > 0 ? PROFIT : value < 0 ? LOSS : INK3) : color;
  const num = p => String(+p.value.toFixed(2)) + unit;
  const lbl = (position, offset, value) => ({ show: true, position, distance: 7, offset,
    formatter: num, color: pointColor(value), fontSize: 10, fontFamily: FONT,
    backgroundColor: 'rgba(255,255,255,0.94)', padding: [3, 4], borderRadius: 2 });
  return {
    symbol: 'circle', symbolSize: 4,
    itemStyle: { color, borderColor: '#fff', borderWidth: 1 },
    data: [
      { type: 'max', itemStyle: { color: pointColor(Math.max(...values)) }, label: lbl(values.indexOf(Math.max(...values)) < values.length / 2 ? 'right' : 'left', [0, (lane || 0) * 16], Math.max(...values)) },
      { type: 'min', itemStyle: { color: pointColor(Math.min(...values)) }, label: lbl(values.indexOf(Math.min(...values)) < values.length / 2 ? 'right' : 'left', [0, -(lane || 0) * 16], Math.min(...values)) }
    ]
  };
}
function tvBaseOption(pointCount) {
  // ai coding: 所有折线图统一单行读数上下留白和日期图例间距 2026/11/06: 16:40
  const legendBase = { icon: 'rect', itemWidth: 14, itemHeight: 3, itemGap: 14,
    textStyle: { color: INK2, fontSize: 11, fontFamily: FONT }, inactiveColor: '#cccccc' };
  return {
    animation: false,
    textStyle: { fontFamily: FONT },
    // ai coding: 所有折线图统一左侧零留白右侧十二像素安全间距 2026/11/06: 18:50
    grid: { left: 0, right: 12, top: 30, bottom: isMobileView ? 30 : 32, containLabel: true },
    // ai coding: 折线图启用双指缩放与单指平移长按时暂停平移 2026/11/06: 16:31
    dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'none',
      start: 0, end: 100, minValueSpan: 1, throttle: 50,
      zoomOnMouseWheel: false, moveOnMouseMove: true, moveOnMouseWheel: false,
      preventDefaultMouseMove: false }],
    legend: isMobileView
      ? { left: 'center', bottom: 0, ...legendBase }
      : { right: 4, top: 2, ...legendBase },
    xAxis: {
      type: 'category', boundaryGap: false,
      axisLine: { lineStyle: { color: RULE } }, axisTick: { show: false },
      // ai coding: 折线图强制显示左右端日期并朝图内对齐避免边缘裁切 2026/11/06: 16:43
      axisLabel: { ...tvAxisLabel, margin: 12, interval: isMobileView ? Math.max(0, Math.ceil(pointCount / 4) - 1) : 'auto', showMinLabel: true, alignMinLabel: 'left', showMaxLabel: true, alignMaxLabel: 'right', hideOverlap: true, formatter: v => String(v).slice(5).replace('-', '/') }
    }
  };
}
// ai coding: ECharts 折线图随窗口尺寸自适应；监听只注册一次、运行时动态取实例，日期筛选重建图表后仍有效 2026/11/06: 14:48
window.addEventListener('resize', () => {
  document.querySelectorAll('#page .echarts-host').forEach(el => {
    const inst = echarts.getInstanceByDom(el);
    if (inst) inst.resize();
  });
});

// ai coding: 重绘所选快照并移除不再展示的 meta 信息和开始日期参数 2026/10/09: 16:03
function renderReport(snapshots, endDate){
  // ai coding: 重绘前清除旧顶部读数避免关闭金额后残留已解锁金额 2026/11/07: 14:13
  document.querySelectorAll('.chart-default-reading').forEach(reading => reading.remove());
  // ai coding: 折线图改用 ECharts 后同步销毁其实例，避免日期筛选重绘时泄漏 2026/11/06: 14:48
  document.querySelectorAll('#page .echarts-host').forEach(el => {
    const inst = echarts.getInstanceByDom(el);
    if (inst) inst.dispose();
  });
  document.querySelectorAll('#page canvas').forEach(canvas => {
    const chart = Chart.getChart(canvas);
    if (chart) chart.destroy();
  });
  document.querySelector('[data-range-notice]')?.remove();
  latest = snapshots[snapshots.length - 1] || {};
  const summary = latest.summary || {};
  const holdings = latest.holdings || [];
  const stats = calculateRangeStats(snapshots);

// ── 01 Overview strip ──
const stripEl = document.getElementById('strip');
const holdingsCurrent = summary.regions?.['整体']?.current ?? summary.holdings_current;
const totalPnl = summary.total_pnl;
const totalRoi = summary.total_roi;
// ai coding: 概览标签使用中文并删除重复序号与缩写 2026/11/06: 16:22
const cells = [
  { num:'持仓总资产', label:'', value: fmtWan(holdingsCurrent), sub:'', cls:'' },
  { num:'区间收益', label:'', value: fmtWan(totalPnl), sub:'', cls: colorClass(totalPnl) },
  { num:'区间收益率', label:'', value: fmtPct(totalRoi), sub:'', cls: colorClass(totalRoi) },
  { num:'最大回撤', label:'', value: stats.max_drawdown != null ? stats.max_drawdown.toFixed(2) + '%' : '—', sub: '', cls:'down' },
];
stripEl.innerHTML = cells.map(c => `
  <div class="cell">
    <div class="num">${c.num}</div>
    <div class="val ${c.cls}">${c.value}</div>
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

// ai coding: 主图 ECharts 双轴折线：系列改名 资产/收益/收益率，默认仅显示收益率（点图例可开另外两条），三实线黑/蓝/橙，十字吸附光标，读数固定左上角单行 2026/11/06: 15:26
// ai coding: 从配置读取三条曲线默认显隐缺失配置时保持仅显示收益率 2026/11/06: 16:38
const summarySeriesConfig = pageConfig?.summary_series || {};
const summarySeriesDefaults = { asset: false, pnl: false, roi: true };
// ai coding: 隐藏金额时主图仅显示收益率曲线避免曲线与刻度泄露资产收益金额 2026/11/07: 14:10
const defaultSeriesVisible = key => !moneyVisible ? key === 'roi' : typeof summarySeriesConfig[key] === 'boolean'
  ? summarySeriesConfig[key] : summarySeriesDefaults[key];
// ai coding: 主图仅一条曲线可见时生成最大最小值标记多条或零条时清空 2026/11/06: 19:25
const masterSelection = { '资产': defaultSeriesVisible('asset'), '收益': defaultSeriesVisible('pnl'), '收益率': defaultSeriesVisible('roi') };
const masterExtrema = {
  '资产': tvExtremum(C_ASSET, '万', 1, assetWan),
  '收益': tvExtremum(C_PNL, '万', 2, pnlWan),
  '收益率': tvExtremum(C_ROI, '%', 0, roiVals)
};
function masterMarkPoint(name, selected) {
  const visible = Object.keys(masterExtrema).filter(key => selected[key] !== false);
  return { ...masterExtrema[name], data: visible.length === 1 && visible[0] === name ? masterExtrema[name].data : [] };
}
const masterChart = echarts.init(document.getElementById('chartMaster'));
masterChart.setOption({
  ...tvBaseOption(dates.length),
  // ai coding: 主图内部左右零留白组件边距仅由外层容器承担避免重复或抵消 2026/11/06: 19:02
  grid: { ...tvBaseOption(dates.length).grid, top: 30, left: 0, right: 0 },
  legend: { ...tvBaseOption(dates.length).legend, data: moneyVisible ? ['资产', '收益', '收益率'] : ['收益率'], selected: { '资产': defaultSeriesVisible('asset'), '收益': defaultSeriesVisible('pnl'), '收益率': defaultSeriesVisible('roi') } },
  tooltip: tvTooltip(p => p.seriesName === '收益率' ? p.value.toFixed(2) + '%' : fmtWan(p.value * 10000)),
  xAxis: { ...tvBaseOption(dates.length).xAxis, data: dates },
  yAxis: [
    { type: 'value', position: 'left',
      axisLine: { show: false }, axisTick: { show: false },
      // ai coding: 主图左轴刻度置于图内避免桌面刻度挤出左侧留白 2026/11/06: 18:49
      axisLabel: { ...tvAxisLabel, color: INK2, show: moneyVisible && !hideYAxisLabel, inside: true, align: 'left', margin: 8 },
      splitLine: { lineStyle: { color: TV_SPLIT } } },
    { type: 'value', position: 'right',
      axisLine: { show: false }, axisTick: { show: false },
      // ai coding: 右轴刻度放入图内避免图表自动追加单侧外部间距 2026/11/06: 19:02
      axisLabel: { ...tvAxisLabel, formatter: '{value}%', show: !hideYAxisLabel, inside: true, align: 'right', margin: 8 },
      splitLine: { show: false } }
  ],
  series: [
    { name: '资产', type: 'line', data: assetWan, yAxisIndex: 0,
      // ai coding: 资产曲线去掉末端名称保留固定灰色与统一线宽 2026/11/06: 19:25
      symbol: 'none', showSymbol: false, endLabel: { show: false },
      smooth: 0.3, lineStyle: { color: C_ASSET, width: LW_MAIN }, itemStyle: { color: C_ASSET },
      // ai coding: 资产极值初始显隐遵循配置中的可见曲线数量 2026/11/06: 19:25
      markPoint: masterMarkPoint('资产', masterSelection) },
    { name: '收益', type: 'line', data: pnlWan, yAxisIndex: 0,
      // ai coding: 收益曲线去掉末端名称保留固定深红与统一线宽 2026/11/06: 19:25
      symbol: 'none', showSymbol: false, endLabel: { show: false },
      smooth: 0.3, lineStyle: { color: C_PNL, width: LW_MAIN }, itemStyle: { color: C_PNL },
      // ai coding: 收益极值初始显隐遵循配置中的可见曲线数量 2026/11/06: 19:25
      markPoint: masterMarkPoint('收益', masterSelection) },
    { name: '收益率', type: 'line', data: roiVals, yAxisIndex: 1,
      // ai coding: 收益率曲线去掉末端名称保留固定深绿与统一线宽 2026/11/06: 19:25
      symbol: 'none', showSymbol: false, endLabel: { show: false },
      smooth: 0.3, lineStyle: { color: C_ROI, width: LW_MAIN }, itemStyle: { color: C_ROI },
      // ai coding: 收益率极值初始显隐遵循配置中的可见曲线数量 2026/11/06: 19:25
      markPoint: masterMarkPoint('收益率', masterSelection) }
  ]
});
bindScrubHaptic(masterChart);
// ai coding: 点击图例后同步极值标记仅为唯一可见曲线显示最大最小值 2026/11/06: 19:25
masterChart.on('legendselectchanged', event => {
  masterChart.setOption({ series: Object.keys(masterExtrema).map(name => ({ name, markPoint: masterMarkPoint(name, event.selected) })) });
});

// ── 03 Drawdown (ECharts 面积线) ──
// ai coding: 回撤曲线和极值使用黑色并将面积改为由白到黑的灰阶渐变 2026/11/06: 15:44
const drawdownChart = echarts.init(document.getElementById('chartDrawdown'));
drawdownChart.setOption({
  ...tvBaseOption(dates.length),
  // ai coding: 回撤内部左右零留白组件配置统一作用于外层 2026/11/06: 19:02
  grid: { ...tvBaseOption(dates.length).grid, left: 0, right: 0 },
  tooltip: tvTooltip(p => p.value.toFixed(2) + '%'),
  xAxis: { ...tvBaseOption(dates.length).xAxis, data: dates },
  yAxis: { type: 'value',
    axisLine: { show: false }, axisTick: { show: false },
    // ai coding: 回撤左轴刻度移入图内确保左侧零留白 2026/11/06: 18:50
    axisLabel: { ...tvAxisLabel, color: INK2, formatter: '{value}%', show: !hideYAxisLabel, inside: true, align: 'left', margin: 8 },
    // ai coding: 回撤分析关闭横向网格线保留纵轴刻度 2026/11/06: 20:02
    splitLine: { show: false } },
  series: [
    { name: '回撤', type: 'line', data: ddOverall, symbol: 'none', smooth: 0.3,
      // ai coding: 回撤曲线与仓位率统一使用同一线宽 2026/11/06: 18:43
      lineStyle: { color: INK, width: LW_MAIN }, itemStyle: { color: INK },
      areaStyle: { origin: 'end', color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(255,255,255,0.06)' },
        { offset: 1, color: 'rgba(0,0,0,0.48)' }
      ]) },
      markPoint: tvExtremum(INK, '%', 0, ddOverall) }
  ]
});
bindScrubHaptic(drawdownChart);

// ── 04 Position rate (ECharts 单折线) ──
const posRateData = snapshots.map(s => (s.summary || {}).holdings_pos_curr_pct);
// ai coding: 仓位率纵轴按有效数据极值上下各增加十个百分点 2026/11/06: 16:22
// ai coding: 仓位率极值标签上下分离最大值置于曲线上方最小值置于下方 2026/11/06: 16:35
const validPositionRates = posRateData.filter(Number.isFinite);
const positionMin = validPositionRates.length ? Math.min(...validPositionRates) - 10 : -10;
const positionMax = validPositionRates.length ? Math.max(...validPositionRates) + 10 : 10;
const positionExtremum = tvExtremum(INK, '%', 0, posRateData);
positionExtremum.data[0].label = { ...positionExtremum.data[0].label, position: 'top', distance: 10, offset: [0, 0] };
positionExtremum.data[1].label = { ...positionExtremum.data[1].label, position: 'bottom', distance: 10, offset: [0, 0] };
const positionChart = echarts.init(document.getElementById('chartPosition'));
positionChart.setOption({
  ...tvBaseOption(dates.length),
  // ai coding: 仓位率内部左右零留白组件配置统一作用于外层 2026/11/06: 19:02
  grid: { ...tvBaseOption(dates.length).grid, left: 0, right: 0 },
  // ai coding: 仓位图图例仅显示仓位曲线不显示辅助网格 2026/11/06: 16:47
  legend: { ...tvBaseOption(dates.length).legend, data: ['仓位'] },
  tooltip: tvTooltip(p => p.value.toFixed(2) + '%'),
  xAxis: { ...tvBaseOption(dates.length).xAxis, data: dates },
  yAxis: { type: 'value', min: positionMin, max: positionMax,
    axisLine: { show: false }, axisTick: { show: false },
    // ai coding: 仓位率左轴刻度移入图内确保左侧零留白 2026/11/06: 18:50
    axisLabel: { ...tvAxisLabel, color: INK2, formatter: '{value}%', show: !hideYAxisLabel, inside: true, align: 'left', margin: 8 },
    splitLine: { show: false } },
  series: [
    { name: '仓位', type: 'line', data: posRateData, symbol: 'none', smooth: 0.3,
      lineStyle: { color: INK, width: LW_MAIN }, itemStyle: { color: INK },
      // ai coding: 仓位率只保留数据曲线和极值删除辅助横向网格系列 2026/11/06: 20:02
      markPoint: positionExtremum }
  ]
});
bindScrubHaptic(positionChart);
// ai coding: 三张折线图初始展示最新值并在交互结束后保留最后查看日期读数同步图例显隐 2026/11/06: 19:42
function bindLatestReading(chart) {
  const host = chart.getDom();
  host.style.position = 'relative';
  const reading = document.createElement('div');
  // ai coding: 标记顶部默认读数供金额切换重绘时清理 2026/11/07: 14:13
  reading.className = 'chart-default-reading';
  reading.style.cssText = 'position:absolute;left:2px;right:16px;top:0;pointer-events:none;z-index:2;overflow:hidden;';
  host.appendChild(reading);
  // ai coding: 回撤分析默认选取区间最大跌幅发生点其他折线图仍默认最新日期 2026/11/06: 20:03
  const maxDrawdownIndex = ddOverall.indexOf(Math.min(...ddOverall.filter(Number.isFinite)));
  let readingIndex = chart === drawdownChart && maxDrawdownIndex >= 0 ? maxDrawdownIndex : dates.length - 1;
  const formatter = chart.getOption().tooltip[0].formatter;
  chart.setOption({ tooltip: { formatter(params) {
    const date = params.find(item => item.seriesType === 'line' && item.value != null)?.axisValue;
    const index = dates.indexOf(date);
    if (index >= 0) readingIndex = index;
    return formatter(params);
  } } });
  const render = () => {
    const option = chart.getOption();
    const selected = option.legend?.[0]?.selected || {};
    const index = readingIndex;
    const params = option.series.filter(series => series.type === 'line' && selected[series.name] !== false).map(series => {
      const color = series.lineStyle?.color || series.itemStyle?.color || INK;
      return { seriesName: series.name, seriesType: 'line', axisValue: dates[index], value: series.data[index],
        marker: '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + color + '"></span>' };
    });
    reading.innerHTML = formatter(params);
  };
  render();
  chart.on('showTip', () => { reading.hidden = true; });
  chart.on('hideTip', () => { render(); reading.hidden = false; });
  chart.on('legendselectchanged', render);
}
[masterChart, drawdownChart, positionChart].forEach(bindLatestReading);

// ai coding: 合并市场仓位为比例条使用高区分度色板并联动完整标的占比列表 2026/11/06: 17:09
const allocationRoot = document.getElementById('portfolioAllocation');
allocationRoot.replaceChildren();
const allocationRows = holdings.filter(h => Number.isFinite(h.current) && h.current > 0)
  .map(h => ({ name: h.name, market: h.market || '其他', value: h.current }))
  .sort((a, b) => b.value - a.value);
const allocationTotal = allocationRows.reduce((sum, row) => sum + row.value, 0);
const allocationMarketNames = { HK: '港股', US: '美股', CN: 'A股' };
// ai coding: 恢复原始绿灰蓝同色系配色并为未来A股保留中性暖灰色系 2026/11/06: 17:12
const allocationTones = {
  HK: { hue: 161, saturation: 21, lightness: 47, step: 7 },
  US: { hue: 205, saturation: 12, lightness: 36, step: 8 },
  CN: { hue: 36, saturation: 12, lightness: 42, step: 7 }
};
const allocationGroups = [];
allocationRows.forEach(row => {
  row.pct = row.value / allocationTotal * 100;
  let group = allocationGroups.find(item => item.market === row.market);
  if (!group) { group = { market: row.market, pct: 0, rows: [] }; allocationGroups.push(group); }
  group.pct += row.pct;
  group.rows.push(row);
});
allocationGroups.sort((a, b) => b.pct - a.pct);
const allocationElement = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};
const allocationLabels = allocationElement('div', 'market-labels');
const allocationBar = allocationElement('div', 'bar');
allocationBar.setAttribute('role', 'img');
allocationBar.setAttribute('aria-label', '各市場分组及标的占总持仓比例');
const allocationLegend = allocationElement('div', 'legend');
allocationRoot.append(allocationLabels, allocationBar, allocationLegend);
let allocationSelected = null;
const selectAllocation = name => {
  allocationSelected = allocationSelected === name ? null : name;
  allocationRoot.querySelectorAll('.segment').forEach(element => {
    element.classList.toggle('active', allocationSelected === element.dataset.name);
    element.classList.toggle('dim', !!allocationSelected && allocationSelected !== element.dataset.name);
  });
  allocationRoot.querySelectorAll('.entry').forEach(element =>
    element.setAttribute('aria-pressed', String(allocationSelected === element.dataset.name)));
};
allocationGroups.forEach(group => {
  const marketName = allocationMarketNames[group.market] || group.market;
  const label = allocationElement('div', 'market-label', marketName);
  label.style.flex = group.pct;
  label.append(allocationElement('span', '', group.pct.toFixed(1) + '%'));
  allocationLabels.append(label);
  const area = allocationElement('div', 'market-segments');
  area.style.flex = group.pct;
  allocationBar.append(area);
  const list = allocationElement('div', 'market-list');
  list.append(allocationElement('div', 'market-list-head', marketName));
  allocationLegend.append(list);
  // ai coding: 按最新快照仓位顺序建立稳定色序日期切换保持标的颜色不变 2026/11/06: 17:12
  const stableNames = [...new Set(allSnapshots.slice().reverse().flatMap(snapshot => (snapshot.holdings || [])
    .filter(row => (row.market || '其他') === group.market).slice().sort((a, b) => (b.current || 0) - (a.current || 0))
    .map(row => row.name)).concat(group.rows.map(row => row.name)))];
  group.rows.forEach(row => {
    const colorIndex = stableNames.indexOf(row.name);
    const tone = allocationTones[group.market] || { hue: 200, saturation: 10, lightness: 44, step: 7 };
    const color = `hsl(${tone.hue} ${tone.saturation}% ${Math.min(85, tone.lightness + colorIndex * tone.step)}%)`;
    const segment = allocationElement('div', 'segment');
    segment.style.flex = row.value;
    segment.style.background = color;
    segment.dataset.name = row.name;
    area.append(segment);
    const entry = allocationElement('button', 'entry');
    entry.type = 'button';
    entry.dataset.name = row.name;
    entry.setAttribute('aria-pressed', 'false');
    entry.setAttribute('aria-label', `${row.name}，${marketName}，占总持仓${row.pct.toFixed(2)}%`);
    const swatch = allocationElement('i', 'swatch');
    swatch.style.background = color;
    entry.append(swatch, allocationElement('span', 'name', row.name), allocationElement('span', 'pct', row.pct.toFixed(1) + '%'));
    entry.addEventListener('click', () => selectAllocation(row.name));
    list.append(entry);
  });
});

// ai coding: 排行按盈亏金额除以当前仓位百分数排序并绘制零仓位或缺失仓位不参与除法 2026/11/07: 13:43
const ranked = holdings.filter(h => Number.isFinite(h.pnl)).map(h => {
  const weight = h.pos_curr_pct;
  const value = Number.isFinite(weight) && weight > 0 ? h.pnl / weight : null;
  return { ...h, rankValue: Number.isFinite(value) ? value : null };
}).sort((a, b) => {
  if (a.rankValue == null || b.rankValue == null) return (a.rankValue == null) - (b.rankValue == null) || b.pnl - a.pnl;
  return b.rankValue - a.rankValue || b.pnl - a.pnl;
});
const rankingHost = document.getElementById('chartRanking');
rankingHost.parentElement.style.height = `${Math.max(ranked.length, 1) * 44 + 60}px`;
const rankAbsMaxWan = Math.max(...ranked.map(h => Math.abs(h.rankValue || 0)), 1) / 10000;
const rankTarget = rankAbsMaxWan * 1.1;
const rankStepBase = Math.pow(10, Math.floor(Math.log10(rankTarget / 3)));
const rankStep = [1, 2, 3, 5, 10].reduce((best, n) =>
  Math.abs(n - rankTarget / 3 / rankStepBase) < Math.abs(best - rankTarget / 3 / rankStepBase) ? n : best, 1) * rankStepBase;
const rankLim = Math.ceil(rankTarget / rankStep) * rankStep;
const rankingChart = echarts.init(rankingHost);
rankingChart.setOption({
  animation: false,
  textStyle: { fontFamily: FONT },
  // ai coding: 为单位仓位盈亏轴名称预留底部空间保持现有细线圆点布局 2026/11/07: 13:43
  grid: { left: isMobileView ? 126 : 180, right: isMobileView ? 74 : 100, top: 8, bottom: 52, containLabel: false },
  tooltip: { show: false },
  xAxis: {
    type: 'value', min: -rankLim, max: rankLim, interval: rankStep,
    name: moneyVisible ? '每1%仓位盈亏（万元）' : '', nameLocation: 'middle', nameGap: 30,
    nameTextStyle: { color: INK3, fontSize: 10, fontFamily: FONT },
    axisLabel: { show: moneyVisible, color: INK3, fontSize: 10, fontFamily: FONT, margin: 12,
      formatter: value => value === 0 ? '0' : Math.abs(value) === rankLim ? value + '万' : '' },
    splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false }
  },
  yAxis: {
    type: 'category', data: ranked.map(h => h.name), inverse: true,
    axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }
  },
  series: [{
    type: 'custom', clip: false, silent: true,
    // ai coding: 线段长度使用归一化盈亏但右侧金额保留实际盈亏 2026/11/07: 13:43
    data: ranked.map((h, index) => [(h.rankValue || 0) / 10000, index]), encode: { x: 0, y: 1 },
    renderItem(params, api) {
      const value = api.value(0);
      const index = api.value(1);
      const zero = api.coord([0, index]);
      const end = api.coord([value, index]);
      const plot = params.coordSys;
      const rowHeight = plot.height / Math.max(ranked.length, 1);
      // ai coding: 归一化线段圆点仍按实际盈亏正负沿用全局深红深绿 2026/11/07: 13:43
      const color = ranked[index].pnl > 0 ? PROFIT : ranked[index].pnl < 0 ? LOSS : INK3;
      return { type: 'group', children: [
        { type: 'line', shape: { x1: zero[0], y1: zero[1] - rowHeight / 2, x2: zero[0], y2: zero[1] + rowHeight / 2 }, style: { stroke: RULE, lineWidth: 1 } },
        // ai coding: 无有效仓位的标的不画归一化线段避免将缺失值误显示为零 2026/11/07: 13:43
        ...(!moneyVisible || ranked[index].rankValue == null ? [] : [
          { type: 'line', shape: { x1: zero[0], y1: zero[1], x2: end[0], y2: end[1] }, style: { stroke: color, lineWidth: 1.5 } },
          { type: 'circle', shape: { cx: end[0], cy: end[1], r: 3.5 }, style: { fill: color } }
        ]),
        { type: 'text', style: { x: 8, y: zero[1], text: ranked[index].name, fill: INK2,
          font: '12px ' + FONT, width: plot.x - 20, overflow: 'break', lineHeight: 16, verticalAlign: 'middle' } },
        { type: 'text', style: { x: api.getWidth() - 8, y: zero[1],
          text: moneyVisible ? (ranked[index].pnl > 0 ? '+' : '') + (ranked[index].pnl / 10000).toFixed(2) + '万' : '—', fill: INK,
          font: '12px ' + FONT, align: 'right', verticalAlign: 'middle' } }
      ] };
    }
  }]
});

// ── 05 Stats grid ──
const statsEl = document.getElementById('statsGrid');
const statItems = [];
statItems.push({ l: '持仓数量', v: stats.holdings_count + ' 只' });
if (stats.max_drawdown != null) statItems.push({ l: '最大回撤', v: stats.max_drawdown.toFixed(2) + '%', cls: 'down' });
if (stats.max_daily_return != null) statItems.push({ l: '最大日收益', v: fmtPct(stats.max_daily_return), cls: colorClass(stats.max_daily_return) });
if (stats.min_daily_return != null) statItems.push({ l: '最大日亏损', v: fmtPct(stats.min_daily_return), cls: colorClass(stats.min_daily_return) });
// ai coding: 标的名称与极值读数分开渲染避免跨列文字重叠 2026/11/06: 16:22
if (stats.max_roi != null) statItems.push({ l: '最大收益率', name: stats.max_roi_name, v: fmtPct(stats.max_roi), cls: colorClass(stats.max_roi) });
if (stats.min_roi != null) statItems.push({ l: '最小收益率', name: stats.min_roi_name, v: fmtPct(stats.min_roi), cls: colorClass(stats.min_roi) });
if (stats.max_pnl != null) statItems.push({ l: '最大收益额', name: stats.max_pnl_name, v: fmtWan(stats.max_pnl), cls: colorClass(stats.max_pnl) });
if (stats.min_pnl != null) statItems.push({ l: '最大亏损额', name: stats.min_pnl_name, v: fmtWan(stats.min_pnl), cls: colorClass(stats.min_pnl) });
statItems.push({ l: '持仓收益率', v: fmtPct(summary.holdings_roi), cls: colorClass(summary.holdings_roi) });
statItems.push({ l: '持仓收益', v: fmtWan(summary.holdings_pnl), cls: colorClass(summary.holdings_pnl) });

// ai coding: 统计数值优先展示标的名称置于独立次行 2026/11/06: 16:22
statsEl.innerHTML = statItems.map(s => `
  <div class="stat">
    <div class="l">${s.l}</div>
    <div class="v ${s.cls || ''}">${s.v}</div>
    ${s.name ? `<div class="n">${s.name}</div>` : ''}
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
    <!-- ai coding: 金额关闭时持仓成本价和现价同样隐藏数量与百分比保留 2026/11/07: 14:10 -->
    <td>${!moneyVisible || isNote ? '—' : (h.cost_price_raw || '—')}</td>
    <td>${moneyVisible ? (h.current_price_raw || '—') : '—'}</td>
    <!-- ai coding: 持仓数量随金额开关隐藏解锁后恢复显示 2026/11/07: 14:18 -->
    <td>${moneyVisible && h.quantity != null ? h.quantity.toLocaleString() : '—'}</td>
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

// ai coding: 留白细线日历按两位有效数字格式化金额支持日月指标切换和双读数详情 2026/11/06: 17:30
(function(){
  const calGrid = document.getElementById('calGrid');
  const calTitle = document.getElementById('calTitle');
  const calDetail = document.getElementById('calDetail');
  const calendarSection = calGrid.closest('.section');
  let view = 'day';
  // ai coding: 金额隐藏时日历默认与切换均仅展示收益率 2026/11/07: 14:10
  let metric = moneyVisible ? 'amt' : 'pct';
  calendarSection.querySelectorAll('[data-metric="amt"]').forEach(button => { button.hidden = !moneyVisible; });
  // ai coding: 日历直接使用数据入口归并后的交易日期与其他组件保持一致 2026/11/07: 13:19
  const initialDate = latest.date || endDate;
  let year = Number(initialDate.slice(0, 4));
  let month = Number(initialDate.slice(5, 7)) - 1;
  let selected = initialDate;
  const key = (y, m, d) => `${y}-${String(m + 1).padStart(2, '0')}` + (d ? `-${String(d).padStart(2, '0')}` : '');
  const pnlMap = {};
  // ai coding: 日历复用统一工作日序列不再二次归并避免日期筛选与月统计口径不一致 2026/11/07: 13:19
  const calendarSnapshots = snapshots.map(snapshot => [snapshot.date, snapshot]);
  let previousCalendarSnapshot = null;
  calendarSnapshots.forEach(([date, snapshot]) => {
    const currentValue = snapshot.summary?.holdings_current;
    if (!Number.isFinite(currentValue)) return;
    if (previousCalendarSnapshot) {
      const previousValue = previousCalendarSnapshot.summary.holdings_current;
      if (previousValue > 0) {
        pnlMap[date] = { amt: Math.round(currentValue - previousValue), pct: (currentValue - previousValue) / previousValue * 100 };
      }
    }
    previousCalendarSnapshot = snapshot;
  });
  const monthMap = {};
  Object.entries(pnlMap).forEach(([date, value]) => {
    const entry = monthMap[date.slice(0, 7)] ||= { amt: 0, pct: null };
    entry.amt += value.amt;
  });
  Object.entries(monthMap).forEach(([date, value]) => {
    // ai coding: 月收益率分母使用归并后的工作日快照确保跨月周末口径一致 2026/11/06: 19:47
    const snapshot = [...calendarSnapshots].reverse().find(([day]) => day.slice(0, 7) <= date)?.[1];
    const total = snapshot?.summary?.regions?.整体?.current;
    value.pct = total > 0 ? value.amt / total * 100 : null;
  });
  // ai coding: 满一万元使用万单位小额显示数字均保留两位有效数字且不使用科学计数法 2026/11/06: 17:30
  function formatCalendarAmount(value) {
    const useWan = Math.abs(value) >= 10000;
    const number = useWan ? value / 10000 : value;
    const formatted = value === 0 ? '0' : new Intl.NumberFormat('zh-CN', {
      minimumSignificantDigits: 2, maximumSignificantDigits: 2, useGrouping: false
    }).format(number);
    return (value > 0 ? '+' : '') + formatted + (useWan ? '万' : '');
  }
  // ai coding: 格内收益率保留一位小数避免窄屏溢出详情保留两位小数 2026/11/06: 17:31
  const formatRate = (value, precision = 2) => value == null ? '—' : (value > 0 ? '+' : '') + value.toFixed(precision) + '%';
  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const activeMap = () => view === 'day' ? pnlMap : monthMap;
  function renderDetail() {
    const value = activeMap()[selected];
    calDetail.replaceChildren(make('span', 'cal-detail-date', selected));
    const values = make('span', 'cal-detail-values');
    const amount = moneyVisible && value ? (value.amt > 0 ? '+' : '') + Math.round(value.amt).toLocaleString('zh-CN') + '元' : '—';
    values.append(make('span', value ? colorClass(value.amt) : '', amount), make('span', value ? colorClass(value.pct) : '', value ? formatRate(value.pct) : '—'));
    calDetail.append(values);
    calGrid.querySelectorAll('[data-date]').forEach(element => element.setAttribute('aria-pressed', String(!element.disabled && element.dataset.date === selected)));
  }
  function render() {
    calTitle.textContent = view === 'day' ? `${year}年${month + 1}月` : `${year}年`;
    calGrid.className = 'cal-grid ' + view;
    calGrid.replaceChildren();
    calendarSection.querySelectorAll('.cal-btn').forEach(button => {
      const active = button.dataset.view === view;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    calendarSection.querySelectorAll('.cal-metric-btn').forEach(button => {
      const active = button.dataset.metric === metric;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const append = (date, label) => {
      const value = activeMap()[date];
      const cell = make('button', 'cal-cell');
      cell.type = 'button';
      cell.dataset.date = date;
      cell.disabled = !value;
      cell.append(make('span', 'day-num', label));
      if (value) {
        const text = metric === 'amt' ? formatCalendarAmount(value.amt) : formatRate(value.pct, 1);
        cell.append(make('span', 'day-value ' + colorClass(value[metric]), text));
        cell.addEventListener('click', () => { selected = date; renderDetail(); });
      }
      // ai coding: 日历无障碍读数在金额关闭时仅报告收益率 2026/11/07: 14:12
      cell.setAttribute('aria-label', date + (value ? (moneyVisible ? `，盈亏${value.amt}元` : '') + `，收益率${formatRate(value.pct)}` : '，无记录'));
      calGrid.append(cell);
    };
    if (view === 'day') {
      // ai coding: 移除周六周日表头与日期格按首个工作日对齐并补齐五列行 2026/11/06: 19:49
      ['一', '二', '三', '四', '五'].forEach(day => calGrid.append(make('div', 'cal-cell weekday', day)));
      const days = new Date(year, month + 1, 0).getDate();
      const workingDays = Array.from({ length: days }, (_, index) => index + 1).filter(day => {
        const weekday = new Date(year, month, day).getDay();
        return weekday >= 1 && weekday <= 5;
      });
      const offset = new Date(year, month, workingDays[0]).getDay() - 1;
      for (let index = 0; index < offset; index++) calGrid.append(make('div', 'cal-cell'));
      workingDays.forEach(day => append(key(year, month, day), String(day)));
      while (calGrid.children.length % 5) calGrid.append(make('div', 'cal-cell'));
    } else {
      for (let currentMonth = 0; currentMonth < 12; currentMonth++) append(key(year, currentMonth), `${currentMonth + 1}月`);
    }
    renderDetail();
  }
  function selectVisibleDate() {
    const prefix = view === 'day' ? key(year, month) : String(year);
    const available = Object.keys(activeMap()).filter(date => date.startsWith(prefix)).sort();
    selected = available[available.length - 1] || (view === 'day' ? key(year, month, 1) : key(year, month));
  }
  document.getElementById('calPrev').onclick = () => navigate(-1);
  document.getElementById('calNext').onclick = () => navigate(1);
  function navigate(delta) {
    if (view === 'month') year += delta;
    else {
      month += delta;
      if (month < 0) { month = 11; year--; }
      if (month > 11) { month = 0; year++; }
    }
    selectVisibleDate(); render();
  }
  // ai coding: 日历单指横滑翻月月视图翻年锁定方向保留纵向滚动并阻止滑动后的误点击 2026/11/06: 19:32
  let calendarSwipe = null;
  let suppressCalendarClickUntil = 0;
  calGrid.addEventListener('touchstart', event => {
    calendarSwipe = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY, dx: 0, direction: null } : null;
  }, { passive: true });
  calGrid.addEventListener('touchmove', event => {
    if (!calendarSwipe || event.touches.length !== 1) { calendarSwipe = null; return; }
    const dx = event.touches[0].clientX - calendarSwipe.x;
    const dy = event.touches[0].clientY - calendarSwipe.y;
    if (!calendarSwipe.direction && Math.max(Math.abs(dx), Math.abs(dy)) >= 8) {
      calendarSwipe.direction = Math.abs(dx) > Math.abs(dy) * 1.2 ? 'horizontal' : 'vertical';
    }
    calendarSwipe.dx = dx;
    if (calendarSwipe.direction === 'horizontal') {
      suppressCalendarClickUntil = Date.now() + 400;
      if (event.cancelable) event.preventDefault();
    }
  }, { passive: false });
  calGrid.addEventListener('touchend', event => {
    if (!calendarSwipe) return;
    const swipe = calendarSwipe;
    calendarSwipe = null;
    if (event.touches.length || swipe.direction !== 'horizontal') return;
    const dx = event.changedTouches[0] ? event.changedTouches[0].clientX - swipe.x : swipe.dx;
    if (Math.abs(dx) >= 48) navigate(dx < 0 ? 1 : -1);
  }, { passive: true });
  calGrid.addEventListener('touchcancel', () => { calendarSwipe = null; }, { passive: true });
  calGrid.addEventListener('click', event => {
    if (Date.now() < suppressCalendarClickUntil) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  calendarSection.querySelectorAll('.cal-btn').forEach(button => button.onclick = () => {
    view = button.dataset.view; selectVisibleDate(); render();
  });
  calendarSection.querySelectorAll('.cal-metric-btn').forEach(button => button.onclick = () => { metric = button.dataset.metric; render(); });
  if (!pnlMap[selected]) selectVisibleDate();
  render();
})();

// ai coding: 直接根据筛选后的快照数量更新单日提示并标记供重绘清理 2026/10/09: 15:59
if (snapshots.length === 1) {
  const n = document.createElement('div');
  n.className = 'notice';
  n.dataset.rangeNotice = 'true';
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
  // ai coding: 使用独立隐藏状态控制空清仓图表以兼容区间切换和模块配置 2026/10/09: 15:58
  document.querySelector('[data-section="closed"]').hidden = closed.length === 0;
  if (closed.length === 0) return;
  new Chart(document.getElementById('chartClosed'), {
    type: 'bar',
    data: {
      labels: closed.map(c => c.name),
      datasets: [{
        // ai coding: 金额关闭时清仓图改画收益率保留非金额信息 2026/11/07: 14:10
        data: closed.map(c => moneyVisible ? c.pnl / 10000 : c.roi),
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

// ai coding: 起止日期默认今年年初至今天，完成任一日期选择后立即刷新 2026/10/09: 16:03
}
const todayParts = new Intl.DateTimeFormat('en', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
}).formatToParts(new Date());
const todayValues = Object.fromEntries(todayParts.map(part => [part.type, part.value]));
const reportToday = `${todayValues.year}-${todayValues.month}-${todayValues.day}`;
const yearStart = todayValues.year + '-01-01';
const dateStart = document.getElementById('dateStart');
const dateEnd = document.getElementById('dateEnd');
const dateFilterStatus = document.getElementById('dateFilterStatus');
dateStart.max = reportToday;
dateEnd.max = reportToday;
dateStart.value = yearStart;
dateEnd.value = reportToday;

// ai coding: 输入初始化与日期变更时同步显示标准年月日格式 2026/11/06: 16:42
function syncDateLabels(){
  [dateStart, dateEnd].forEach(input => {
    document.getElementById(input.id + 'Display').textContent = input.value;
  });
}
function applyDateRange(){
  syncDateLabels();
  const startDate = dateStart.value;
  const endDate = dateEnd.value;
  if (!startDate || !endDate || startDate > endDate || endDate > reportToday) {
    dateFilterStatus.textContent = '请选择有效日期：开始不得晚于结束，结束不得晚于今天。';
    return;
  }
  const selectedSnapshots = allSnapshots.filter(snapshot => snapshot.date >= startDate && snapshot.date <= endDate);
  if (!selectedSnapshots.length) {
    dateFilterStatus.textContent = '所选区间没有快照，请调整日期；当前保留上次有效区间的报告。';
    return;
  }
  dateFilterStatus.textContent = '';
  renderReport(selectedSnapshots, endDate);
}
[dateStart, dateEnd].forEach(input => input.addEventListener('change', applyDateRange));
applyDateRange();

</script>
<script>
async function downloadElementAsPng(element, filename, horizontalPadding = 0, verticalPadding = 0){
  const renderScale = 2;
  const canvas = await html2canvas(element, {
    scale: renderScale,
    useCORS: true,
    backgroundColor: '#ffffff',
    // ai coding: 截图副本解除祖先横向裁切并展开时间线避免滚动区域外内容丢失 2026/11/07: 14:01
    windowWidth: Math.max(document.documentElement.clientWidth, element.scrollWidth),
    onclone(clonedDocument, clonedElement) {
      if (!element.classList.contains('section-export-mode')) return;
      for (let ancestor = clonedElement.parentElement; ancestor; ancestor = ancestor.parentElement) {
        ancestor.style.setProperty('overflow', 'visible', 'important');
        ancestor.style.setProperty('overflow-x', 'visible', 'important');
        ancestor.style.setProperty('overflow-y', 'visible', 'important');
        ancestor.style.setProperty('max-width', 'none', 'important');
        ancestor.style.setProperty('min-width', element.offsetWidth + 'px', 'important');
      }
      clonedElement.querySelectorAll('.ht-scroll,.table-scroll').forEach(scroller => {
        scroller.style.setProperty('overflow', 'visible', 'important');
        scroller.scrollLeft = 0;
        scroller.scrollTop = 0;
      });
      clonedElement.querySelectorAll('.ht-name').forEach(name => name.style.setProperty('position', 'static', 'important'));
    }
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
  // ai coding: 板块导出图片时同步触发 ECharts 折线图重排尺寸 2026/11/06: 14:48
  section.querySelectorAll('.echarts-host').forEach(el => {
    const inst = echarts.getInstanceByDom(el);
    if (inst) inst.resize();
  });
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

// ai coding: 复用整容器导出流程展开滚动内容保存后恢复布局滚动位置并阻止重复下载 2026/11/07: 13:57
const exportingSections = new WeakSet();
async function downloadSection(section) {
  if (!section || exportingSections.has(section)) return;
  exportingSections.add(section);
  const originalCursor = document.body.style.cursor;
  const originalWidth = section.style.width;
  const scrollers = Array.from(section.querySelectorAll('.table-scroll,.ht-scroll'));
  const scrollPositions = scrollers.map(element => [element, element.scrollLeft, element.scrollTop]);
  const buttons = Array.from(section.querySelectorAll('.section-download-btn'));
  const measureWidth = () => Math.ceil(Math.max(1120, section.scrollWidth, ...scrollers.map(element => element.scrollWidth + section.offsetWidth - element.clientWidth)));
  try {
    buttons.forEach(button => { button.disabled = true; button.style.visibility = 'hidden'; });
    document.body.style.cursor = 'wait';
    const width = measureWidth();
    section.classList.add('section-export-mode');
    section.style.width = width + 'px';
    scrollers.forEach(element => { element.scrollLeft = 0; element.scrollTop = 0; });
    await waitForExportLayout();
    section.style.width = measureWidth() + 'px';
    resizeSectionCharts(section);
    await waitForExportLayout();
    // ai coding: 持仓明细与时间线导出图片上下各增加六像素留白 2026/11/07: 14:00
    const verticalPadding = ['holdings', 'timeline'].includes(section.dataset.section) ? 6 : 0;
    await downloadElementAsPng(section, 'portfolio_' + section.dataset.section + '_' + (latest.date || 'report') + '.png', 16, verticalPadding);
  } finally {
    section.classList.remove('section-export-mode');
    section.style.width = originalWidth;
    resizeSectionCharts(section);
    await waitForExportLayout();
    scrollPositions.forEach(([element, left, top]) => { element.scrollLeft = left; element.scrollTop = top; });
    document.body.style.cursor = originalCursor;
    buttons.forEach(button => { button.style.visibility = ''; button.disabled = false; });
    exportingSections.delete(section);
  }
}
// ai coding: 仅持仓明细和时间线标题支持桌面双击手机双点及键盘下载不显示下载图标 2026/11/07: 13:57
document.querySelectorAll('.section-head h2').forEach(title => {
  const section = title.closest('.section');
  if (['holdings', 'timeline'].includes(section.dataset.section)) {
    title.setAttribute('role', 'button');
    title.tabIndex = 0;
    title.setAttribute('aria-label', title.textContent.trim() + '，双击下载图片');
    title.addEventListener('dblclick', event => { event.preventDefault(); downloadSection(section); });
    title.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); downloadSection(section); }
    });
    let lastTap = null;
    title.addEventListener('touchend', event => {
      if (event.touches.length || event.changedTouches.length !== 1) { lastTap = null; return; }
      const touch = event.changedTouches[0], now = Date.now();
      if (lastTap && now - lastTap.time < 350 && Math.hypot(touch.clientX - lastTap.x, touch.clientY - lastTap.y) < 24) {
        event.preventDefault(); lastTap = null; downloadSection(section);
      } else lastTap = { time: now, x: touch.clientX, y: touch.clientY };
    }, { passive: false });
    return;
  }
  if (pageConfig.section_download_buttons === false) return;
  const downloadButton = document.createElement('button');
  downloadButton.type = 'button';
  downloadButton.className = 'section-download-btn';
  downloadButton.setAttribute('aria-label', '下载' + title.textContent.trim() + '图片');
  downloadButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 5-5m-5 5-5-5M5 21h14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  title.insertAdjacentElement('afterend', downloadButton);

  downloadButton.addEventListener('click', event => {
    event.preventDefault();
    downloadSection(section);
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
      th.style.textAlign = 'center';
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
      + '<td style="text-align:center">' + nav.toFixed(4) + '</td>'
      + '<td style="text-align:center;color:' + color + ';font-weight:600;">' + (d.return >= 0 ? '+' : '') + d.return.toFixed(2) + '%</td>';
    if (showBench) {
      benchNames.forEach(name => {
        const bench = benchmarks[name];
        const entry = bench.data.find(b => b.year === d.year);
        if (entry) {
          const c = entry.return >= 0 ? PROFIT : LOSS;
          html += '<td style="text-align:center;color:' + c + ';">' + (entry.return >= 0 ? '+' : '') + entry.return.toFixed(2) + '%</td>';
        } else {
          html += '<td style="text-align:center;">—</td>';
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
    let html = '<td style="font-weight:700;padding:4px 12px 4px 8px;white-space:nowrap;">整体</td>'
      + '<td style="text-align:center;font-weight:600;padding:8px;">' + (stats.annual_cumulative_nav || 0).toFixed(4) + '</td>'
      + '<td style="text-align:center;padding:8px;color:' + color + ';font-weight:700;">' + (cagr >= 0 ? '+' : '') + cagr.toFixed(2) + '%</td>';
    if (showBench) {
      benchNames.forEach(name => {
        const b = benchmarks[name];
        if (b.cagr != null) {
          const c = b.cagr >= 0 ? PROFIT : LOSS;
          html += '<td style="text-align:center;padding:8px 16px;color:' + c + ';font-weight:700;">' + (b.cagr >= 0 ? '+' : '') + b.cagr.toFixed(2) + '%</td>';
        } else {
          html += '<td style="text-align:center;padding:8px 16px;">—</td>';
        }
      });
    }
    const tr = document.createElement('tr');
    // ai coding: 汇总行分隔线统一由表格细线样式控制 2026/11/06: 18:27
    tr.innerHTML = html;
    if (tfoot) tfoot.appendChild(tr);
  }
})();
</script>
<script>
// ai coding: 按配置将章节追加到页眉之后而不再以顶部更新时间作为插入锚点 2026/10/09: 15:58
// Apply config: order sections exactly as listed, then hide disabled sections.
if (pageConfig && pageConfig.sections) {
  const page = document.getElementById('page');
  const allSections = Array.from(document.querySelectorAll('.section[data-section]'));
  const configuredSections = Object.keys(pageConfig.sections)
    .map(id => document.querySelector('[data-section="' + id + '"]'))
    .filter(Boolean);
  const configuredSet = new Set(configuredSections);
  const orderedSections = configuredSections.concat(
    allSections.filter(section => !configuredSet.has(section))
  );

  if (page) {
    orderedSections.forEach(section => page.appendChild(section));
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
    # ai coding: 按配置生成 HTML 时间线没有交易时隐藏空内容 2026/11/06: 18:24
    timeline_html = generate_timeline_html(config)

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
            # ai coding: 仅允许已定义主题并将未知配置回退到原始白底 2026/11/06: 19:16
            .replace("__PAGE_THEME__", config.get("theme") if config.get("theme") in ("soft_shadow", "warm_gray", "plain") else "plain")
            # ai coding: 日期筛选关闭时直接写入隐藏样式无需等待 JavaScript 2026/11/06: 18:48
            .replace("__DATE_FILTER_VISIBILITY__", 'style="display:none"' if config.get("date_filter") is False else '')
            # ai coding: 将原生时间线内容写入报告模板 2026/11/06: 18:24
            .replace("__TIMELINE_HTML__", timeline_html)
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
    # ai coding: 生成报告后自动同步网页入口避免配置修改只写入 report 而页面仍用旧值 2026/11/06: 19:01
    public_dir = os.path.join(script_dir, "public")
    os.makedirs(public_dir, exist_ok=True)
    public_file = os.path.join(public_dir, "index.html")
    with open(output_file, "r", encoding="utf-8") as report_file:
        html = report_file.read()
    with open(public_file, "w", encoding="utf-8") as page_file:
        page_file.write(html)

    print(f"[OK] 报告已生成: {output_file}")
    # ai coding: 显示已同步的网页入口便于确认配置已写入实际页面 2026/11/06: 19:01
    print(f"     网页入口已同步: {public_file}")
    print(f"     快照数量: {len(snapshots)}")
    print(f"     最新日期: {stats.get('latest_date', 'N/A')}")
    print(f"     持仓数量: {stats.get('holdings_count', 0)}")


if __name__ == "__main__":
    main()
