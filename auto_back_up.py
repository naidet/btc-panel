#!/usr/bin/env python3
"""
BTC交易系统 - 自动备份脚本
运行后自动提交所有改动到 git，防止误删/误改
"""
import subprocess, sys, os
from datetime import datetime

os.chdir("D:/BTC")

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()

# 检查是否有改动
status = run("git status --porcelain")
if not status:
    print("✅ 没有改动，无需备份")
    sys.exit(0)

# 显示将要备份的文件
print("📦 准备备份以下文件:")
for line in status.splitlines():
    f = line.split()[-1]
    print(f"  {line[0:2]} {f}")

print()

# 提交
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
run("git add -A")
r = subprocess.run(f'git commit -m "自动备份 {now}"', shell=True, capture_output=True, text=True)
print(r.stdout or r.stderr)

# 显示最近3次提交
print("\n📜 最近备份记录:")
print(run("git log --oneline -5"))
