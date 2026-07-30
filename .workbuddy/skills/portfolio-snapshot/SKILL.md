---
name: portfolio-snapshot
description: "每日持仓快照自动化：读取腾讯文档持仓表 → 拉取 westock 实时行情 → 计算盈亏 → 生成 HTML 报告 → 部署公网。触发词：更新持仓、跑一下快照、获取最新数据、生成报告、刷新报告、部署、run the pipeline、snapshot the portfolio。"
agent_created: true
---

# Portfolio Snapshot Pipeline

一站式执行每日持仓快照全流程：腾讯文档 → 实时行情 → 快照 → 报告 → 部署。

## 前置条件

- 腾讯文档 Token（从 https://docs.qq.com/scenario/open-claw.html 获取）
- westock-mcp 连接器已连接
- `snapshot_live.py` 和 `generate_report.py` 在项目目录中
- 腾讯文档 file_id: `fGemVXqsvRGM`

## 执行步骤

按顺序执行，任何步骤失败则报告错误并停止。

### 1. 确定路径

- `{PYTHON}` = `C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`
- `{PROJECT}` = 当前工作区目录
- `{TOKEN}` = 腾讯文档 API Token（用户提供）

### 2. 读取腾讯文档

**方案A（优先）**：用 `mcp__tencent-docs__sheet.get_cell_data`（file_id=fGemVXqsvRGM, sheet_id=000001, return_csv=true）。提取 csv_data。

**方案B（MCP 工具不可用时）**：用 Python urllib 直接调 API：

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

### 3. 解析并修复 CSV

用 Python `csv.reader` 解析 content。提取从表头行（含"公司名称"）到"收益率"行的所有数据，写入 `{PROJECT}/.tmp_csv.csv`。

**三个必须执行的修复：**

#### 3a. 列偏移修复
遍历持仓行，若 `row[1]`（市场列）不在 `{CN, HK, US, ""}` 中且能转为 float（如 "0.441187"），说明列偏移——去掉 `row[0]`，整体左移一位。

```python
VALID_MARKETS = {'CN', 'HK', 'US', ''}
if mkt and mkt not in VALID_MARKETS and not past_total:
    try:
        float(mkt)
        r = r[1:] + ['']  # 左移
    except ValueError: pass
```

#### 3b. 短行修复（如 SMMT Call 期权）
若 `row[3]`（代码列）不是有效股票代码（不匹配 `\d{4,6}\.(SH|SZ|HK)` 或 `[A-Z]+\.US`），说明是短行——数据被压缩到了前几列，实际应在 col10（投入）和 col11（当前）。

```python
import re
code = row[3].strip()
if code and not re.match(r'^\d{4,6}\.(SH|SZ|HK)$', code) and not re.match(r'^[A-Z]+\.US$', code):
    row = row[:3] + [''] * 7 + row[3:]  # 插入7个空列，数据右移到正确位置
```

#### 3c. 汇总行完整性
确保 CSV 包含以下行（在"总计"行之后）：
- `年初` → year_start
- `工资结余` → salary_surplus
- `基数` → base
- `收益` → total_pnl
- `收益率` → total_roi

缺少任何一行，total_pnl 或 total_roi 会为 null，报告对应位置显示空。

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
- 总收益（total_pnl）、总收益率（total_roi）
- 公网链接（deploy 返回的 shareLink）

### 9. 清理

删除 `{PROJECT}/.tmp_csv.csv` 和 `{PROJECT}/.tmp_prices.json`。

## 已知问题与修复记录

| 问题 | 根因 | 修复 |
|------|------|------|
| 康方生物数据错位 | CSV 行首有市场权重数字（0.441187），导致列偏移 | 3a 列偏移修复 |
| 总收益率显示 -0.13% | total_roi 是小数（-0.1265），fmtPct 未 *100 | snapshot_live.py 中 parse_percent 后 *100 |
| total_pnl/total_roi 为 null | CSV 缺少"收益"/"收益率"行 | 3c 确保汇总行完整 |
| SMMT Call 投入/当前为 0 | 短行（5列）数据被误放到代码/成本价列 | 3b 短行修复 |
| MCP 工具不可用 | 连接器未在会话启动时注册 | 方案B：HTTP API + Bearer token |
| PowerShell 中文乱码 | Out-File 双重 UTF-8 编码 | 全程用 Python 处理 |

## 关键文件

| 文件 | 作用 |
|------|------|
| `snapshot_live.py` | CSV + 价格JSON → 快照JSON（含列偏移/短行修复、total_roi *100） |
| `generate_report.py` | 快照JSON → HTML报告（无股息列、isNote处理无成本价持仓） |
| `config.json` | 控制页面模块显隐 |
| `portfolio_snapshots/*.json` | 每日快照存档 |
| `deploy/index.html` | 部署用 HTML |

## 异常处理

- 任何步骤失败 → 报告错误，不生成空文件
- 当天 JSON 已存在 → 覆盖更新
- MCP 工具不可用时自动走方案B
- CSV 列偏移/短行自动修复
- 完成后始终清理临时文件
