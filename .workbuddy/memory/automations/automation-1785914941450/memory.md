# 自动化任务记忆：每日持仓快照（automation-1785914941450）

## 执行记录

### 2026-09-02（首次执行成功）
- 数据源：腾讯文档 fGemVXqsvRGM（tdoc_init 缺宿主 token，改用 MCP get_content 成功）
- 行情：westock-mcp data_quote 一次调用获取 7 只持仓 + 沪深300 + 纳斯达克
- 快照：portfolio_snapshots/2026-09-02.json（8 只持仓，含 SMMT Call 270115）
- 报告：report.html → deploy/index.html → 部署成功（shareLink: https://167b54fec43844e3986f9ea901a55bff.bj9.agentos-app.net）
- Git：commit 8a209f3 成功；push 失败（直连 github 超时、代理 127.0.0.1:7890 未运行），需手动补推
- 关键数据：投入 234.67万、当前 217.95万、持仓收益 -16.72万(-7.12%)、总收益 -41.05万、总收益率 -15.89%
- 基准：沪深300 YTD -0.40% / CAGR -1.47%；纳斯达克 YTD +12.30% / CAGR +11.80%
- 临时文件已清理（.tmp_csv.csv/.tmp_prices.json/.tmp_raw.json/.tmp_benchmarks.json）

## 经验备忘
- tdoc_init 需宿主注入 token，本环境不可用；直接用 mcp__tencent-docs__get_content 读取，content 为纯 CSV 文本
- 部署工具实际名为 workbuddy_sites_deploy（旧名 workbuddy_cloudstudio_deploy 已废弃），directory=deploy/，language=static
- push 前若直连失败先试代理；本机代理未常驻运行
