"""
BTC panel build script
Output: D:\BTC\dist\BTC交易面板.exe
"""
import os, sys, shutil, subprocess

os.chdir("D:/BTC")
for d in ["build", "dist"]:
    if os.path.exists(d): shutil.rmtree(d)

# build flat arg list
args = [
    sys.executable, "-m", "PyInstaller",
    "--onefile", "--windowed",
    "--name", "BTC交易面板",
    "--icon", "btc_icon.ico",
    "--clean", "--noconfirm",
]

hidden = ["MetaTrader5", "numpy", "requests", "pickle", "threading",
          "json", "tkinter", "winsound", "subprocess"]
for h in hidden:
    args += ["--hidden-import", h]

for f in ["kline_model.pkl", "signal_filters.py", "binance_depth.py", "btc_trader.py", "license.py"]:
    if os.path.exists(f):
        args += ["--add-data", f"{f};."]

args.append("btc_panel.py")

print("Building...")
r = subprocess.run(args, timeout=300)
if r.returncode == 0:
    exe = "dist/BTC交易面板.exe"
    if os.path.exists(exe):
        s = os.path.getsize(exe) / 1024 / 1024
        print(f"\nDone: D:\\BTC\\{exe} ({s:.1f} MB)")
    else:
        print("\nEXE not found, check dist/")
else:
    print(f"\nFailed: {r.returncode}")
