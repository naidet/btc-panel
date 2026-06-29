"""
BTC Panel build script v5
Output: D:\BTC\dist\BTC_Panel\  (onedir, ASCII-safe)
"""
import os, sys, shutil, subprocess

os.chdir("D:/BTC")

# Clean previous
for d in ["build", "dist"]:
    try:
        if os.path.exists(d):
            shutil.rmtree(d)
    except: pass

SRC = "."

args = [
    sys.executable, "-m", "PyInstaller",
    "--onedir", "--noconsole",
    "--name", "BTC_Panel",
    "--icon", os.path.join(SRC, "btc_icon.ico"),
    "--clean", "--noconfirm",
]

# 排除运行时用不到的大包
exclude_modules = [
    "matplotlib", "pandas",
    "PIL", "cv2",
]
for m in exclude_modules:
    args += ["--exclude-module", m]

# Hidden imports
hidden = [
    "MetaTrader5", "numpy",
    "PySide6", "PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui",
    "PySide6.QtNetwork",
    "pickle", "threading", "json", "time", "datetime", "math",
    "os", "collections", "importlib", "importlib.util",
    "warnings", "pathlib",
    "urllib.request", "hashlib",
    "hmmlearn", "hmmlearn.hmm",
    "scipy", "scipy._external", "scipy._external.array_api_compat",
    "scipy._external.array_api_compat.numpy_fft",
    "sklearn", "sklearn.metrics",
]
for h in hidden:
    args += ["--hidden-import", h]

# Data files
data_files = [
    ("btc_trader.py", "."),
    ("license.py", "."),
    ("hmm_state.py", "."),
    ("updater.py", "."),
    ("hmm_model.pkl", "."),
    ("btc_icon.ico", "."),
]

for fname, dest in data_files:
    fp = os.path.join(SRC, fname)
    if os.path.exists(fp):
        args += ["--add-data", fp + ";" + dest]

# symbols/ 目录 (仅含 xauusd 和 btcusd)
sym_dir = os.path.join(SRC, "symbols")
if os.path.isdir(sym_dir):
    args += ["--add-data", sym_dir + ";symbols"]

# Main entry
args.append(os.path.join(SRC, "btc_panel_qt.py"))

print(f"Building ONEDIR from {SRC}/ ...")
print(f"  Hidden imports: {len(hidden)}")
print(f"  Excluded modules: {exclude_modules}")
print()

r = subprocess.run(args, timeout=600)
if r.returncode == 0:
    exe_dir = "dist/BTC_Panel"
    exe = os.path.join(exe_dir, "BTC_Panel.exe")
    if os.path.exists(exe):
        total_size = 0
        for root, dirs, files in os.walk(exe_dir):
            for f in files:
                total_size += os.path.getsize(os.path.join(root, f))
        print(f"\nDone: {exe} ({total_size/1024/1024:.1f} MB total)")
    else:
        print(f"\nEXE not found, check {exe_dir}/")
        for f in os.listdir("dist"):
            print(f"  {f}")
else:
    print(f"\nFailed: {r.returncode}")
