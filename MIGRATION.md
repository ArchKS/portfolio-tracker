# 迁移指南：把「每日持仓快照」搬到另一台电脑

本功能由 4 部分组成，其中**只有项目文件夹是可整体带走的**，另外 3 项是机器本地状态，需在新机器重建。

---

## 哪些能带走 / 哪些不能

| 组件 | 是否可迁移 | 说明 |
|------|-----------|------|
| 项目文件夹（本目录） | ✅ 直接拷贝 | 含 `portfolio_snapshot.py` / `generate_report.py` / `run_daily.py` / `portfolio_snapshots/`（历史快照）/ `deploy/` / `report.html` |
| 脚本依赖 | ✅ 无需重装 | 三个脚本只用 Python 标准库（csv/json/os/glob/datetime/subprocess），**不需要 pip 安装任何包** |
| 历史快照 `portfolio_snapshots/*.json` | ✅ 随文件夹走 | 迁移后趋势图/回撤自动带上已有历史 |
| 腾讯文档连接器登录态 | ❌ 需重连 | 新机器在 WorkBuddy 里重新连接「腾讯文档」连接器（同一腾讯账号） |
| 腾讯文档 file_id `fGemVXqsvRGM` | ✅ 稳定不变 | 这是文档在云端的固定 ID，连上连接器后 MCP 读取直接可用 |
| WorkBuddy 自动化任务 | ❌ 需重建 | 任务存在本机 SQLite（`~/.workbuddy/workbuddy.db`），不随项目走；且提示词里硬编码了本机的绝对路径 |
| CloudStudio 公网链接 | ❌ 会变 | 同一目录部署 sandboxId 通常不变，但访问 host/URL 可能随 CloudStudio 调度变化；**以每次部署返回的 shareLink 为准**，需更新书签 |

---

## 迁移步骤

### 1. 带走项目文件夹
把整个项目目录（含上述所有文件）拷到新电脑：U 盘、网盘、git 均可。
无需安装 Python 包；新机器只要有 WorkBuddy 自带的托管 Python（3.13）即可。

### 2. 新机器连接腾讯文档连接器
在 WorkBuddy 左侧连接器面板找到「腾讯文档」，点击连接并登录**同一个腾讯账号**（即拥有/可访问该持仓文档的账号）。
验证：在对话里让我 `search_file 持仓` 能搜到 file_id `fGemVXqsvRGM` 即可。

### 3. 重建自动化任务
用下面**参数化提示词模板**创建任务（任务 → 新建自动化，或让我执行 automation_update）。
需替换两处占位符：
- `{PYTHON}`：新机器托管 Python 路径，通常为
  `C:\Users\<用户名>\.workbuddy\binaries\python\versions\3.13.12\python.exe`
  （Mac/Linux 为 `~/.workbuddy/binaries/python/versions/3.13.12/python.exe`）
- `{PROJECT}`：新机器上的项目目录绝对路径

> 路径分隔符：Windows 用 `\`，Mac/Linux 用 `/`。

### 4. 首次运行 + 拿新链接
手动触发一次任务验证。最后一步 `workbuddy_cloudstudio_deploy` 会返回**新链接**，把它替换掉旧书签即可。

---

## 参数化自动化提示词模板

```
执行每日持仓快照并部署公网报告。先把下方 {PYTHON} 和 {PROJECT} 替换为新机器实际值。

{PYTHON} = 托管 Python 绝对路径
{PROJECT} = 项目目录绝对路径（含 run_daily.py 的那一层）

步骤：
1. 用 mcp__tencent-docs__sheet.get_cell_data 读取持仓表：
   file_id="fGemVXqsvRGM", sheet_id="000001",
   start_row=0, end_row=163, start_col=0, end_col=12, return_csv=true
   提取返回里的 csv_data 字段。
2. 将 csv_data 写入文件：{PROJECT}/.tmp_portfolio_csv.csv
3. 执行命令：{PYTHON} {PROJECT}/run_daily.py
   （该脚本会：CSV→JSON 快照 → 生成 report.html → 复制到 deploy/index.html）
4. 调用 workbuddy_cloudstudio_deploy，参数 directory = {PROJECT}/deploy
   （返回的 shareLink 即最新公网链接；历史链接可能因缓存或调度失效，需更新书签）
5. 简要报告：持仓数量、总收益、总收益率（用文档值）、以及第4步返回的最新公网链接。

异常处理：
- 第1步腾讯文档读取失败 → 报错，不要生成空文件
- 当天 JSON 已存在 → 覆盖更新
- 完成后清理 {PROJECT}/.tmp_portfolio_csv.csv
```

建议调度：每日 15:00（你更新文档后）。

---

## 常见问题

- **Q：历史快照会丢吗？** 不会，只要 `portfolio_snapshots/` 随文件夹一起拷走，趋势/回撤图就有完整历史。
- **Q：为什么链接会变？** CloudStudio sandbox 是云端运行实例，虽然 sandboxId 通常不变，但访问 host 可能随 CloudStudio 调度变化，且旧链接可能有缓存；请以每次部署返回的 shareLink 为准。
- **Q：能否让链接也固定？** 可改用你自己的固定托管（如国内对象存储 / 自有域名）。当前方案为 CloudStudio 零配置，故接受换机换链。
- **Q：脚本在新机器要装依赖吗？** 不用，纯标准库。
