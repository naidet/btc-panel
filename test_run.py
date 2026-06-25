#!/usr/bin/env python3
"""
测试运行面板但不显示GUI
"""
import sys
import os
import traceback

os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

try:
    print("尝试导入模块...")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    
    # 创建应用但不显示
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 导入主窗口类
    print("导入主窗口类...")
    exec(open("btc_panel_qt.py", encoding="utf-8").read().split("def main():")[0])
    
    # 从导入的代码中获取MainWindow类
    from btc_panel_qt import MainWindow
    
    print("创建主窗口实例...")
    window = MainWindow()
    
    # 设置一个定时器来检测窗口是否创建成功
    def check_window():
        if window.isVisible():
            print("✅ 窗口创建成功！")
        else:
            print("窗口已创建但未显示")
        app.quit()
    
    QTimer.singleShot(1000, check_window)
    
    print("开始应用事件循环...")
    sys.exit(app.exec())
    
except Exception as e:
    print(f"❌ 错误发生: {e}")
    traceback.print_exc()
    input("按Enter键退出...")