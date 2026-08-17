---
name: portfolio-snapshot
description: "每日持仓快照自动化：读取腾讯文档持仓表 → 拉取 westock 实时行情 → 计算盈亏 → 生成 HTML 报告 → 部署公网。触发词：更新持仓、跑一下快照、获取最新数据、生成报告、刷新报告、部署、run the pipeline、snapshot the portfolio。"
agent_created: true
---

# Portfolio Snapshot Pipeline

一站式执行每日持仓快照全流程：腾讯文档 → 实时行情 → 快照 → 报告 → 部署。

## 前置条件

- tencent-docs 连接器已连接（或腾讯文档 Token）
- westock-mcp 连接器已连接
- `snapshot_live.py`、`generate_report.py`、`config.json`、`deploy/` 在 skill 目录中
- 腾讯文档 file_id: `fGemVXqsvRGM`

## 执行步骤

按顺序执行，任何步骤失败则报告错误并停止。

### 1. 确定路径

- `{PYTHON}` = `/Users/zendu/.workbuddy/binaries/python/versions/3.13.12/bin/python3`
- `{PROJECT}` = skill 目录（`~/.workbuddy/skills/portfolio-snapshot/`），脚本和数据均在此目录
- `{TDOC_SKILL}` = `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/builtin-plugins/tencent-docs-plugin/skills/tencent-docs`（实际路径含 `plugins/workbuddy-builtin` 层级，旧路径 `.../resources/builtin-plugins/...` 已失效；若 App 升级路径变动，用 `find "$(dirname "$(dirname "$(dirname "$(dirname "$(dirname "$(dirname "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources")")")")")")" -name tencentdocs.py 2>/dev/null` 搜索定位）

### 2. 读取腾讯文档

**方案A（优先）**：用 tencent-docs skill 的 `tdoc_call` 入口（宿主注入票据，无需 Token）：

```bash
cd "{TDOC_SKILL}" && "{PYTHON}" tencentdocs.py tdoc_init  # 检查就绪
cd "{TDOC_SKILL}" && "{PYTHON}" tencentdocs.py tdoc_call tencent-docs get_content '{"file_id":"fGemVXqsvRGM"}' > "{PROJECT}/.tmp_raw.json"
```

从 `.tmp_raw.json` 提取 `result.structuredContent.content`（CSV 格式文本）。

**方案B（MCP 工具不可用时）**：用 Python urllib 直接调 API（需 Token）：

```python
import json, urllib.request
url = 'https://docs.qq.com/openapi/mcp'
body = json.dumps({'jsonrpc':'2.0','method':'tools/call','params':{'name':'get_content','arguments':{'file_id':'fGemVXqsvRGM'}},'id':1}).encode()
req = urllib.request.Request(url, data=body, headers={'Authorization':f'Bearer {TOKEN}','Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=30) as r:
    result = json.loads(r.read())
content = json.loads(result['result']['content'][0]['text'])['content']
```

⚠️ 不要用 PowerShell 的 `Out-File` 保存中文内容（会双重 UTF-8 编码），直接用 Python 处理。

### 3. 解析 CSV

用 Python `csv.reader` 解析 content。定位表头行（**0-based 索引 r[1]="市场"、r[2] 含"公司名称"**，表头首列 r[0] 为空字符串；不要用 r[2]/r[3] 匹配，会定位失败）和结束行（row[1]="收益率"，**必须匹配 row[1] 而非 row[0]**——文档后部年度收益表头行 row[0]="收益率"（如 idx 269）也会匹配 row[0]，取第一个 row[1] 匹配才是汇总行（如 idx 24），否则段落过长会混入清仓复盘/收支/年度收益表等无关数据）。提取从 `max(0, header-3)` 到 `收益率` 行的段（含汇率行），写入 `{PROJECT}/.tmp_csv.csv`。

⚠️ **不需要手动做列偏移/短行修复**——`snapshot_live.py` 内部已处理（短行自动 pad、总计行/股息列对齐）。

CSV 必须包含以下汇总行（在"总计"行之后），供脚本提取：
- `年初` → year_start（基数计算用）
- `工资结余` → salary_surplus（基数计算用）
- `基数` → base（收益计算的分母）
- `收益` / `收益率` → **不再使用**，收益和收益率由脚本自算

### 4. 提取代码并获取行情

从 CSV col3 提取所有以 .SH/.SZ/.HK/.US 结尾的值。转换格式：

| CSV 代码 | westock 代码 |
|----------|-------------|
| 600585.SH | sh600585 |
| 09926.HK | hk09926 |
| PDD.US | usPDD |

逗号拼接，调用 `mcp__westock-mcp__data_quote`。

从返回结果提取 `price` 字段，转回 CSV 格式 key，写入 `{PROJECT}/.tmp_prices.json`：

```json
{"600585.SH": 18.64, "09926.HK": 93.9, ...}
```

### 4b. 获取基准指数 YTD

读取 `config.json` 中 `annual_returns_benchmarks`，若 `show` 为 `true`：

- 从 `indices` 取各指数的 `code`（如 `sh000300`、`usIXIC`）
- 逗号拼接，调用 `mcp__westock-mcp__data_quote`
- 从返回结果提取每个指数的 `chg_ytd` 字段（YTD 涨跌幅%）
- 写入 `{PROJECT}/.tmp_benchmarks.json`：

```json
{"沪深300": 0.61, "纳斯达克": 14.38}
```

若调用失败或 `chg_ytd` 缺失，跳过该指数（报告中年化为空）。`generate_report.py` 会自动读取此文件。

### 5. 生成快照

```bash
"{PYTHON}" "{PROJECT}/snapshot_live.py" "{PROJECT}/.tmp_csv.csv" "{PROJECT}/.tmp_prices.json"
```

### 6. 生成报告

```bash
"{PYTHON}" "{PROJECT}/generate_report.py"
```

### 7. 部署

```bash
cp "{PROJECT}/report.html" "{PROJECT}/deploy/index.html"
```

调用 `workbuddy_cloudstudio_deploy`，directory = `{PROJECT}/deploy`。

### 8. 报告结果

- 持仓数量、投入总额、当前市值
- 持仓收益（金额+百分比）
- 总收益（total_pnl，自算）、总收益率（total_roi，自算，两位小数）
- 基准对比（沪深300/纳斯达克 YTD + CAGR，若 config 中 show=true）
- 公网链接（deploy 返回的 shareLink）
- Git commit hash（步骤 10）

**计算公式**（snapshot_live.py 内部）：
- 仓位分母 = 文档"整体"投入/当前（含现金调整，非纯持仓总额）
- 固定现金差额 = 文档整体当前 - 文档持仓当前（不随行情变）
- 实时整体当前 = 实时持仓当前 + 固定现金差额
- 个股收益率 roi = (现价 - 成本价) / 成本价 × 100（纯股价涨幅，不受汇率/数量影响；无现价或成本价时为 None）
- 个股 pnl = 当前市值 - 投入（人民币金额口径）
- total_pnl = 实时整体当前 - 基数（基数 = 年初 + 工资结余/2）
- total_roi = total_pnl / 基数 × 100（保留两位小数）
- 已平仓持仓收益率 = (卖出价 - 成本价) / 成本价 × 100（generate_report.py，缺失时回退投入口径）

**持仓明细现金行**（generate_report.py 前端 JS）：
- 现金当前 = 整体当前 - 持仓当前（可为负数）
- 现金投入 = 整体投入 - 持仓投入
- 现金仓位占比 = 现金当前 / 整体当前 × 100（负数正常显示）
- 现金收益、收益率 → 显示"—"（不计算）

**年化收益率表基准对比**（generate_report.py，config 中 `annual_returns_benchmarks.show=true` 时显示）：
- 沪深300（sh000300）、纳斯达克（usIXIC）各年收益从 config.json 读取（2022-2025）
- 2026 YTD 从 `.tmp_benchmarks.json` 读取（westock `chg_ytd` 字段，实时获取）
- 基准累计净值 = ∏(1 + 各年收益率)
- 基准 CAGR = (累计净值) ^ (1 / 年数) - 1

### 9. 清理

删除 `{PROJECT}/.tmp_csv.csv`、`{PROJECT}/.tmp_prices.json`、`{PROJECT}/.tmp_raw.json`、`{PROJECT}/.tmp_benchmarks.json`。

### 10. Git 提交并推送

```bash
cd "{PROJECT}"
git add -A
git commit -m "每日持仓快照 $(date +%Y-%m-%d)"
git push origin main
```

若 `git push` 因网络失败，重试一次。报告结果中附上 commit hash。

## 已知问题与修复记录

| 问题 | 根因 | 修复 |
|------|------|------|
| 康方生物数据错位 | CSV 行首有市场权重数字（0.441187），导致列偏移 | snapshot_live.py 内部短行 pad 修复 |
| 总收益率显示 -0.13% | total_roi 是小数（-0.1265），fmtPct 未 *100 | snapshot_live.py 中 parse_percent 后 *100 |
| SMMT Call 投入/当前为 0 | 短行（5列）数据被误放到代码/成本价列 | snapshot_live.py 内部自动 pad |
| MCP 工具不可用 | 连接器未在会话启动时注册 | 方案B：HTTP API + Bearer token |
| PowerShell 中文乱码 | Out-File 双重 UTF-8 编码 | 全程用 Python 处理 |
| 仓位占比对不上文档 | 分母用了纯持仓总额（2,419,490）而非"整体"（2,407,490） | pos_cost_pct/pos_curr_pct 分母改为 overall_inv/overall_cur |
| regions 未提取 | 代码检查 row[9] 但"整体"标签在 row[8] | col8 检查改为 row[8]，数据列同步调整 |
| 收益/收益率用的是文档旧值 | total_pnl/total_roi 直接读文档"收益"/"收益率"行 | 改为自算：`整体当前 - 基数`、`收益/基数×100`，保留两位小数 |
| 整体当前不随行情更新 | overall_cur 直接取文档固定值 | 改为 `实时持仓当前 + 固定现金差额`（差额=文档整体当前-文档持仓当前） |
| 总计行 doc_invested/current 为 null | 总计行数据左对齐（col5/6/7），代码读 col11/12/13 | 总计行列索引改为 col5/6/7 |
| 个股股息全为 None | 股息在 col12，代码读 col13 | 股息列改为 col12；holdings_dividends 改为个股合计 |
| 美股/港股收益率虚高 | `__main__` 中 `meta["exchange_rates"]=summary.pop("exchange_rates",None)` 把 parse_holdings 提取到的汇率覆盖为 None，build_snapshot 永远用默认 US=6.78/HK=0.86 | 改为 `summary["exchange_rates"]=meta.get("exchange_rates") or summary.pop(...)`，让 build_snapshot 读到文档真实汇率（US>RMB 6.7505） |
| CSV 列偏移/短行需手动修复 | 旧流程在步骤3手动修复 | snapshot_live.py 内部已处理，步骤3只需提取原始段 |
| 结束行被年度收益表头覆盖 | 文档后部还有"收益率 2022 2023..."表头行也匹配"收益率"关键字，解析循环若取最后一个匹配会把 end_idx 覆盖成 269，段落过长 | 解析循环取**第一个**"收益率"匹配后立即 break；表头/结束行定位都用 `xxx is None` 守卫 |

## 关键文件

| 文件 | 作用 |
|------|------|
| `snapshot_live.py` | CSV + 价格JSON → 快照JSON（内部处理短行pad、总计行/股息列对齐；仓位分母用"整体"；收益/收益率自算） |
| `generate_report.py` | 快照JSON → HTML报告（isNote处理无成本价持仓；持仓明细末尾追加"现金"行，显示投入/当前/仓位占比，收益和收益率为"—"；仓位占比负数正常显示） |
| `config.json` | 控制页面模块显隐；annual_returns_history 历史收益；annual_returns_benchmarks 基准对比(沪深300/纳斯达克) |
| `portfolio_snapshots/*.json` | 每日快照存档 |
| `deploy/index.html` | 部署用 HTML |

## 异常处理

- 任何步骤失败 → 报告错误，不生成空文件
- 当天 JSON 已存在 → 覆盖更新
- MCP 工具不可用时自动走方案B
- CSV 短行/列偏移由 snapshot_live.py 内部自动处理
- 收益/收益率自算，不依赖文档"收益"/"收益率"行
- 完成后始终清理临时文件（.tmp_csv.csv、.tmp_prices.json、.tmp_raw.json、.tmp_benchmarks.json）
- 清理后执行 git add + commit + push（临时文件已被 .gitignore 忽略，快照和报告会提交）
