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

### 2026-09-29 06:01（当日首次）
- 数据源：腾讯文档 fGemVXqsvRGM（`tdoc_call tencent-docs get_content` 落 .tmp_raw.json，一次成功）。CSV header idx=2 / end idx=19；8 行持仓（7 只 + SMMT Call）无变动；汇率 US 6.6958 / HK 0.8531；整体基数 258.30万（年初 250.50万 + 工资结余 7.80万/2）
- 行情：westock-mcp data_quote **一次批量取全 9 码**（7 持仓 + sh000300 + usIXIC），无限频无漏码。行情 time 全部 = 2026-09-28（周一）。康方 92.00 -1.66%、SMMT 15.48 -0.83%、海螺 15.75 +0.38%、亚盛 29.48 +2.01%、传奇 18.62 -2.56%、新氧 2.69 -0.37%、汇贤 0.325 持平
- 基准：沪深300 YTD -6.25%（较 09-28 的 -4.12% 明显回落，CSI300 当日 -2.22%）；纳斯达克 YTD +15.40%
- 快照：portfolio_snapshots/2026-09-29.json（第 65 份）；报告 report.html → deploy/index.html
- 部署：workbuddy_sites_deploy 仍报"预留域名 portfolio-snapshot-96971.app.workbuddy.host 未绑定"；curl 旧链接 https://167b54fec43844e3986f9ea901a55bff.bj9.agentos-app.net 含 2026-09-29 06:01:22（HTTP 200），公网链接不变
- 关键数据：持仓投入 228.21万、持仓当前 218.24万、持仓收益 -9.98万(-4.37%)、总收益 -41.46万、总收益率 -16.05%（较 09-28 的 -40.46万/-15.66% 回落，主因 A 股/港股 09-28 普跌）
- 基准：沪深300 YTD -6.25% / CAGR -2.56%；纳斯达克 YTD +15.40% / CAGR +11.59%
- Git：commit a5c4f33；push 成功（836cc72..a5c4f33，一次成功）
- 临时文件已清理

## 经验备忘
- tdoc_init 需宿主注入 token，本环境不可用；直接用 tencent-docs CLI `tdoc_call` 读取，content 为纯 CSV 文本
- 部署工具实际名为 workbuddy_sites_deploy（旧名 workbuddy_cloudstudio_deploy 已废弃），directory=deploy/，language=static
- 部署工具长期报"预留域名未绑定"（已知故障），不重试，改 curl 旧链接验证当日数据
- push 前若直连失败先试代理；本机代理未常驻运行
- sh000300 遇 A 股节假日休市时 time 落后，属正常，不要重试

### 2026-09-30 06:01（当日首次）
- 数据源：腾讯文档 fGemVXqsvRGM（`tdoc_call tencent-docs get_content` 一次成功），CSV header idx=2 / end idx=19；8 行（7 只 + SMMT Call）无变动；汇率 US 6.6958 / HK 0.8531；基数 258.30万
- 行情：westock-mcp data_quote **一次批量取全 9 码**（7 持仓 + sh000300 + usIXIC），无限频无漏码。行情 time 全部 = 2026-09-29（周二）。康方 106.30 +15.54%（放量大涨，volume_ratio 4.95）、SMMT 16.39 +5.88%、亚盛 30.36 +2.99%、传奇 18.82 +1.07%、海螺 15.90 +0.95%、新氧 2.71 +0.74%、汇贤 0.32 -1.54%
- 基准：沪深300 YTD -6.15%（09-29 收盘 4345.21 +0.10%）；纳斯达克 YTD +15.30%
- 快照：portfolio_snapshots/2026-09-30.json（第 66 份）；report.html → deploy/index.html
- 部署：workbuddy_sites_deploy 报"预留域名 portfolio-snapshot-95207 未绑定"（已知故障，未重试）；curl 旧链接 https://167b54fec43844e3986f9ea901a55bff.bj9.agentos-app.net 含 2026-09-30 06:01:09 与 2343055.16（HTTP 200），公网链接不变
- 关键数据：持仓投入 228.21万、持仓当前 234.31万、持仓收益 +6.09万(+2.67%)、总收益 -25.39万、总收益率 -9.83%（较 09-29 的 -9.98万/-4.37% 持仓、-41.46万/-16.05% 总口径大幅回升，主因创新药板块普涨）
- 基准：沪深300 YTD -6.15% / CAGR -2.52%；纳斯达克 YTD +15.30% / CAGR +11.51%
- Git：commit 3d0db8b；push **失败**（代理 127.0.0.1:7890 未运行，直连 SSL_ERROR_SYSCALL），本地 main ahead 2（含 09-29 未推的一笔）
- 临时文件已清理
- 备注：`data_quote` 批量一次成功（连续第五日）；文档"收益/收益率"行数值陈旧（-301383/-11.668%，与其自身整体口径自洽但落后于行情），脚本按规范自算，未受影响

### 2026-10-01 06:01（当日首次）
- 数据源：腾讯文档 fGemVXqsvRGM（`tdoc_call tencent-docs get_content` 一次成功），CSV header idx=2 / end idx=19；8 行（7 只 + SMMT Call）无变动；汇率 US 6.6958 / HK 0.8531；基数 258.30万
- 行情：westock-mcp data_quote **一次批量取全 9 码**（7 持仓 + sh000300 + usIXIC），无限频无漏码。行情 time 全部 = 2026-09-30（周三）。康方 108.70 +2.26%、SMMT 16.91 +3.17%、亚盛 30.74 +1.25%、海螺 16.17 +1.70%、传奇 19.89 +5.69%、新氧 2.67 -1.48%、汇贤 0.325 +1.56%；沪深300 4357.62 +0.29%
- 基准：沪深300 YTD -5.88%（前档 -6.15% × 当日 +0.29%，验算通过）；纳斯达克 YTD +15.57%（前档 +15.30% × 当日 +0.24%，验算通过）
- 快照：portfolio_snapshots/2026-10-01.json（第 67 份）；report.html → deploy/index.html
- 部署：workbuddy_sites_deploy 报"预留域名 portfolio-snapshot-19807 未绑定"（已知故障，未重试）；curl 旧链接 https://167b54fec43844e3986f9ea901a55bff.bj9.agentos-app.net 含 2026-10-01 06:01:42（HTTP 200），公网链接不变
- 关键数据：持仓投入 228.21万、持仓当前 239.11万、持仓收益 +10.89万(+4.77%)、总收益 -20.59万、总收益率 -7.97%（较 09-30 的 -25.39万/-9.83% 继续回升，连续两日走强，创新药与 SMMT 齐涨）
- 基准：沪深300 YTD -5.88% / CAGR -2.48%；纳斯达克 YTD +15.57% / CAGR +11.62%；组合 YTD -7.97% / CAGR +26.18%
- Git：commit ed1f44f；push **失败**（代理 127.0.0.1:7890 未运行，直连 SSL_ERROR_SYSCALL，两次尝试均失败）；本地 main ahead 5（09-29/09-30 累积未推 + 本日）
- 临时文件已清理
- 备注：`data_quote` 批量一次成功（连续第六日）；文档"收益/收益率"行仍为陈旧值（-301383/-11.668%），脚本自算不受影响
