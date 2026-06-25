#!/usr/bin/env python3
"""
测试面板启动 - 最小化版本
"""
import sys, os
os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

# 基本UI测试
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from PySide6.QtCore import Qt

print("开始创建应用...")
app = QApplication(sys.argv)

print("创建窗口...")
window = QMainWindow()
window.setWindowTitle("测试面板")
window.setGeometry(100, 100, 800, 600)

label = QLabel("BTC AI 交易面板 - 测试启动", window)
label.setAlignment(Qt.AlignmentFlag.AlignCenter)
window.setCentralWidget(label)

print("显示窗口...")
window.show()

print("应用启动成功，准备执行...")
sys.exit(app.exec())