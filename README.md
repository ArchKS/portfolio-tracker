# Portfolio Snapshot

拉取持仓信息、保存每日快照并生成单文件 HTML 投资组合报告。

## 生成报告

```powershell
python generate_report.py
```

运行后会生成：

- `report.html`：完整投资组合报告，内含重仓股持有时间线模块。
- `timeline.svg`：可单独使用的买入到清仓时间线。

## 时间线配置

时间线的交易记录和显示设置统一维护在 `config.json` 的 `timeline` 节点：

- `trades`：标的名称、买入/清仓日期、本金、利润和年化收益率。
- `show_amount`：是否显示具体利润与仓位。
- `layout`：时间线尺寸。

页面模块可通过 `sections.timeline` 显示或隐藏。

只生成独立 SVG：

```powershell
python generate_timeline.py
```
