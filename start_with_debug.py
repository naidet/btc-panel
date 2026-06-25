#!/usr/bin/env python3
"""
启动原始面板，但捕获调试信息
"""
import sys, os, traceback, threading
from io import StringIO

# 重定向标准输出
original_stdout = sys.stdout
original_stderr = sys.stderr

# 创建一个输出捕获器
output_buffer = StringIO()

class TeeOutput:
    def __init__(self, buffer, original):
        self.buffer = buffer
        self.original = original
    
    def write(self, text):
        self.buffer.write(text)
        self.original.write(text)
    
    def flush(self):
        self.buffer.flush()
        self.original.flush()

sys.stdout = TeeOutput(output_buffer, original_stdout)
sys.stderr = TeeOutput(output_buffer, original_stderr)

print("=" * 60)
print("BTC AI交易面板 - 调试启动")
print("=" * 60)

os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

# 先检查依赖
print("\n1. 检查依赖...")
try:
    import PySide6
    print("   ✅ PySide6 版本:", PySide6.__version__)
except ImportError:
    print("   ❌ PySide6 未安装")
    sys.exit(1)

try:
    import MetaTrader5 as mt5
    print("   ✅ MetaTrader5 可用")
except ImportError:
    print("   ⚠️ MetaTrader5 未安装，将使用模拟模式")

try:
    import pandas as pd
    print("   ✅ pandas 版本:", pd.__version__)
except ImportError:
    print("   ❌ pandas 未安装")

try:
    import numpy as np
    print("   ✅ numpy 版本:", np.__version__)
except ImportError:
    print("   ❌ numpy 未安装")

# 检查文件
print("\n2. 检查文件...")
files_to_check = ['btc_panel_qt.py', 'btc_panel.py', 'panel_params.json']
for f in files_to_check:
    if os.path.exists(f):
        print(f"   ✅ {f} 存在")
    else:
        print(f"   ❌ {f} 不存在")

# 尝试导入主模块
print("\n3. 导入主模块...")
try:
    # 尝试导入
    print("   尝试导入 btc_panel_qt...")
    import btc_panel_qt as panel_module
    print("   ✅ btc_panel_qt 导入成功")
    
    # 启动应用
    print("\n4. 启动应用...")
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    print("   创建窗口...")
    window = panel_module.MainWindow() if hasattr(panel_module, 'MainWindow') else panel_module.BTCTradingPanel()
    
    print("   显示窗口...")
    window.show()
    
    print("\n✅ 应用启动成功！")
    print("窗口已显示，进入事件循环...")
    
    sys.exit(app.exec())
    
except Exception as e:
    print(f"\n❌ 启动失败: {e}")
    print("\n详细错误信息:")
    traceback.print_exc()
    
    # 保存日志
    with open("startup_debug.log", "w") as f:
        f.write(output_buffer.getvalue())
    
    print(f"\n日志已保存到: startup_debug.log")
    input("\n按Enter键退出...")