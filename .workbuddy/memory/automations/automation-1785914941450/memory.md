# 自动化任务记忆：每日持仓快照（automation-1785914941450）

## 执行记录

### 2026-09-28 06:01（当日首次）
- 数据源：腾讯文档 fGemVXqsvRGM（tencent-docs CLI `tdoc_call tencent-docs get_content` 落 .tmp_raw.json，成功）。7 只持仓 + SMMT Call 共 8 行，无变动；汇率 US 6.6958 / HK 0.8531；文档整体基数 258.30万（年初 250.50万 + 工资结余 7.80万/2）
- 行情：westock-mcp data_quote **一次批量取全 9 码**（7 持仓 + 沪深300 + usIXIC），无限频无漏码。行情 time：港股/美股=2026-09-25 收盘（A 股 09-25 中秋休市），沪深300 time=2026-09-24。康方 93.55 -0.37%、SMMT 15.61 -4.70%、海螺 15.69 -1.38%、亚盛 28.90 -0.69%、传奇 19.11 +0.26%、新氧 2.70 持平、汇贤 0.325 +1.56%
- 基准：沪深300 YTD -4.12%（time 09-24，A 股休市沿用）；纳斯达克 YTD +16.46%
- 快照：portfolio_snapshots/2026-09-28.json（新增，第 64 份）；报告 report.html → deploy/index.html
- 部署：workbuddy_sites_deploy 仍报"预留域名 portfolio-snapshot-11896.app.workbuddy.host 未绑定"；curl 验证旧链接 https://167b54fec43844e3986f9ea901a55bff.bj9.agentos-app.net 已含 2026-09-28 数据（snapshot_time 06:01:00，total_pnl -404606，HTTP 200），公网链接不变
- 关键数据：持仓投入 228.21万、持仓当前 219.24万、持仓收益 -8.97万(-3.93%)、总收益 -40.46万、总收益率 -15.66%（与 09-26 完全持平——09-26/28 行情同为 09-25 收盘，周末无新交易）
- 基准：沪深300 YTD -4.12% / CAGR -2.12%；纳斯达克 YTD +16.46% / CAGR +11.79%
- Git：commit 1d2da9d；push 成功（958c124..1d2da9d，一次成功）
- 临时文件已清理
- 备注：本档 `data_quote` 批量一次成功（连续第四日）；数据与 09-26 完全一致（同一交易日收盘），属正常

## 经验备忘
- tdoc_init 需宿主注入 token，本环境不可用；直接用 tencent-docs CLI `tdoc_call` 读取，content 为纯 CSV 文本
- 部署工具实际名为 workbuddy_sites_deploy（旧名 workbuddy_cloudstudio_deploy 已废弃），directory=deploy/，language=static
- 部署工具长期报"预留域名未绑定"（已知故障），不重试，改 curl 旧链接验证当日数据
- push 前若直连失败先试代理；本机代理未常驻运行
- sh000300 遇 A 股节假日休市时 time 落后，属正常，不要重试
