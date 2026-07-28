import subprocess, shutil, os

os.chdir(r"C:\Users\Administrator\WorkBuddy\2026-07-27-11-53-42")
py = r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"

# CSV already saved from MCP read - let me just use the snapshot_live.py
subprocess.run([py, "snapshot_live.py", ".tmp_csv.csv", ".tmp_prices.json"], check=True)
subprocess.run([py, "generate_report.py"], check=True)
shutil.copy("report.html", "deploy/index.html")
print("DONE")