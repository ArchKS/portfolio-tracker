import subprocess, shutil, os, json

os.chdir(r"C:\Users\Administrator\WorkBuddy\2026-07-27-11-53-42")
py = r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"

# Prices with correct code format
prices = {"600585.SH":17.71,"09926.HK":96.55,"06855.HK":35.42,"LEGN.US":19.27,
          "SMMT.US":13.11,"03613.HK":6.76,"00696.HK":8.53,"02669.HK":3.44,
          "06049.HK":28.04,"PDD.US":84.85,"SY.US":1.97,"87001.HK":0.38}
with open(".tmp_prices.json","w") as f: json.dump(prices,f)

# Step 1: snapshot
subprocess.run([py,"snapshot_live.py",".tmp_csv.csv",".tmp_prices.json"],check=True)
# Step 2: report
subprocess.run([py,"generate_report.py"],check=True)
# Step 3: deploy
shutil.copy("report.html","deploy/index.html")
print("ALL DONE")
# Cleanup
for f in [".tmp_csv.csv",".tmp_prices.json"]:
    try: os.remove(f)
    except: pass