"""
打包序列号生成器为带图标的 EXE
"""
import os, sys, subprocess, shutil

os.chdir("D:/BTC")

# 清理
for d in ["build_keygen", "dist_keygen"]:
    if os.path.exists(d):
        shutil.rmtree(d)

args = [
    sys.executable, "-m", "PyInstaller",
    "--onefile", "--windowed",
    "--name", "序列号生成器",
    "--icon", "btc_icon.ico",
    "--distpath", "dist_keygen",
    "--workpath", "build_keygen",
    "--clean", "--noconfirm",
]

for f in ["license.py", "btc_icon.ico"]:
    if os.path.exists(f):
        args.insert(-1, "--add-data")
        args.insert(-1, f"{f};.")

args.append("keygen_gui.py")

print("正在打包序列号生成器...")
r = subprocess.run(args, timeout=300)

if r.returncode == 0:
    exe = "dist_keygen/序列号生成器.exe"
    if os.path.exists(exe):
        # 复制到桌面
        desktop = os.path.expanduser("~/Desktop")
        dest = os.path.join(desktop, "序列号生成器.exe")
        shutil.copy(exe, dest)
        s = os.path.getsize(dest) / 1024 / 1024
        print(f"\n✅ 完成: 桌面\\序列号生成器.exe ({s:.1f} MB)")
        # 删除旧的 bat
        bat = os.path.join(desktop, "序列号生成器.bat")
        if os.path.exists(bat):
            os.remove(bat)
            print("   已删除旧的 .bat 文件")
    else:
        print("\n❌ EXE 未生成")
else:
    print(f"\n❌ 失败: {r.returncode}")
