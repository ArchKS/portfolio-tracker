# -*- coding: utf-8 -*-
"""
每日更新合并入口（为迁移/自动化而设）

把原来分散的 3 步合并成 1 条命令，减少自动化里硬编码的路径数量：
  1. 读取临时 CSV → 生成 JSON 快照 (portfolio_snapshot.py)
  2. 读取所有快照 → 生成 report.html (generate_report.py)
  3. 复制 report.html → deploy/index.html

用法（在自动化中调用，仅需传入 python 二进制一次）：
  python run_daily.py

CSV 输入约定：脚本同级目录下的 .tmp_portfolio_csv.csv
所有路径均基于 __file__，跨机器/跨平台可直接拷贝使用。
"""

import os
import sys
import shutil
import subprocess


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, ".tmp_portfolio_csv.csv")

    if not os.path.exists(csv_path):
        print("Error: 找不到临时 CSV 文件 ->", csv_path, file=sys.stderr)
        print("       请先由腾讯文档 MCP 读取持仓表并写入该文件。", file=sys.stderr)
        sys.exit(1)

    # 1. 生成 JSON 快照
    subprocess.run(
        [sys.executable, os.path.join(script_dir, "portfolio_snapshot.py"), csv_path],
        check=True,
    )

    # 2. 生成 HTML 报告
    subprocess.run(
        [sys.executable, os.path.join(script_dir, "generate_report.py")],
        check=True,
    )

    # 3. 复制到 deploy/index.html（供 CloudStudio 部署）
    src = os.path.join(script_dir, "report.html")
    dst_dir = os.path.join(script_dir, "deploy")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, "index.html")
    shutil.copy(src, dst)

    print("[OK] 每日更新完成：JSON 快照 + report.html + deploy/index.html 已就绪")


if __name__ == "__main__":
    main()
