---
name: portfolio-snapshot
description: "This skill should be used when the user wants to run a daily portfolio snapshot: read holdings from Tencent Docs, pull real-time prices from westock-mcp, calculate PnL, generate an HTML report, and deploy to CloudStudio. Trigger phrases: 跑一下快照, 更新持仓, 获取最新数据, 生成报告, 刷新报告, 部署, run the pipeline, snapshot the portfolio."
agent_created: true
---

# Portfolio Snapshot Pipeline

One-shot execution of the full daily portfolio pipeline:
read Tencent Docs → pull live prices → compute P&L → generate report → deploy.

## Prerequisites

- Tencent Docs connector connected (file_id: `fGemVXqsvRGM`)
- westock-mcp connector connected
- `snapshot_live.py` and `generate_report.py` exist in the project directory

## Execution

Run every step sequentially. Stop and report the error if any step fails.

### 1. Determine paths

The project directory is the session workspace. The Python executable
is the managed Python interpreter. If unsure, run:

```
python -c "import sys; print(sys.executable)"
```

Store the result as `{PYTHON}` and the project directory as `{PROJECT}`.

### 2. Read the Tencent Docs spreadsheet

Use `mcp__tencent-docs__sheet.get_cell_data`:

| param | value |
|-------|-------|
| file_id | `fGemVXqsvRGM` |
| sheet_id | `000001` |
| start_row | 0 |
| end_row | 163 |
| start_col | 0 |
| end_col | 14 |
| return_csv | true |

Extract the `csv_data` field from the response.

### 3. Save CSV

Write `csv_data` to `{PROJECT}/.tmp_csv.csv` (use the Write tool).

### 4. Pull live prices

Extract all non-empty stock codes from the CSV column 3 (the 「代码」 column).
Filter to entries ending with .SH, .SZ, .HK, or .US.
Convert to westock format:

- `XXX.SH` → `sh` + XXX (e.g. `600585.SH` → `sh600585`)
- `XXX.SZ` → `sz` + XXX
- `XXX.HK` → `hk` + XXX  (e.g. `09926.HK` → `hk09926`)
- `XXX.US` → `us` + XXX (uppercase, e.g. `PDD.US` → `usPDD`)

Join with commas and call `mcp__westock-mcp__data_quote`. This ensures
new stocks added to the spreadsheet are automatically picked up.

For each stock in the response, extract the `price` field.

Westock returns codes like `sh600585` — convert them to the CSV format
by stripping the prefix and adding the suffix:

| westock code | CSV code |
|-------------|----------|
| sh600585 | 600585.SH |
| hk09926 | 09926.HK |
| usLEGN | LEGN.US |

Build a JSON object:

```json
{"600585.SH": 17.71, "09926.HK": 96.55, ...}
```

Write it to `{PROJECT}/.tmp_prices.json`.

### 5. Compute snapshot

Run:

```bash
"{PYTHON}" "{PROJECT}/snapshot_live.py" "{PROJECT}/.tmp_csv.csv" "{PROJECT}/.tmp_prices.json"
```

### 6. Generate report

Run:

```bash
"{PYTHON}" "{PROJECT}/generate_report.py"
```

### 7. Deploy

Copy the report and deploy:

```bash
cp "{PROJECT}/report.html" "{PROJECT}/deploy/index.html"
```

Then call `workbuddy_cloudstudio_deploy` with `directory = "{PROJECT}/deploy"`.

### 8. Report results

Briefly report:

- Number of holdings, total P&L amount and rate (from the document's
  summary rows, NOT from the computed holdings)
- The public URL — always use the `shareLink` returned by
  `workbuddy_cloudstudio_deploy`

### 9. Cleanup

Delete `{PROJECT}/.tmp_csv.csv` and `{PROJECT}/.tmp_prices.json`.

## Error handling

- If step 2 (Tencent Docs) fails → report the error, do not create empty files
- If step 4 (westock) fails → report the error
- If the day's JSON snapshot already exists → overwrite it
- Always run cleanup (step 9) regardless of success or failure

## Notes

- Stock codes are extracted dynamically from the CSV 「代码」 column.
  Adding or removing stocks in the spreadsheet requires no code changes.
- The `app.codebuddy.work` domain has CDN caching; the
  `e2b.ap-beijing.sandbox.cloudstudio.club` URL is direct and
  updates instantly. Use whichever `shareLink` is returned.
