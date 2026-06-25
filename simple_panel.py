#!/usr/bin/env python3
"""
简化版BTC交易面板 - 仅UI测试
"""
import sys, os, json, time, threading
from datetime import datetime

os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

# 模拟btc_panel模块
import types
btc_panel_module = types.ModuleType('btc_panel')
btc_panel_module.load_params = lambda: json.load(open("panel_params.json")) if os.path.exists("panel_params.json") else {}
btc_panel_module.save_params = lambda x: json.dump(x, open("panel_params.json", "w"), indent=2)
btc_panel_module.execute_trade = lambda *args: print(f"模拟交易: {args}")
btc_panel_module.fetch_all_mt5_data = lambda: {}
btc_panel_module.check_risk_gates = lambda: True
btc_panel_module.get_daily_pnl = lambda: 0.0
btc_panel_module._mt5_lock = threading.RLock()
btc_panel_module.MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
btc_panel_module.DEFAULT_PARAMS = {}
btc_panel_module.SYMBOLS = []
btc_panel_module.SYMBOL_NAMES = {}
btc_panel_module.SYMBOL_PARAMS = {}
sys.modules['btc_panel'] = btc_panel_module

# 模拟MetaTrader5
mt5_module = types.ModuleType('MetaTrader5')
mt5_module.initialize = lambda **kwargs: print(f"Mock MT5初始化"); True
mt5_module.shutdown = lambda: None
sys.modules['MetaTrader5'] = mt5_module

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QTextEdit, QFrame, QScrollArea,
    QMenuBar, QMenu, QStatusBar, QSizePolicy, QGridLayout, QGroupBox,
    QLineEdit, QCheckBox, QSplitter, QToolTip
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QRect
from PySide6.QtGui import QFont, QColor, QPalette, QAction, QIcon, QPainter, QBrush, QPen

class SimpleBTCTradingPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BTC AI 交易面板 (简化版)")
        self.setGeometry(100, 100, 1024, 768)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 标题
        title = QLabel("🚀 BTC AI 自动交易系统")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00a86b; margin: 20px;")
        main_layout.addWidget(title)
        
        # 状态信息
        status_widget = QGroupBox("系统状态")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("✅ 系统正常 - 简化版运行中")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 16px; padding: 10px;")
        status_layout.addWidget(self.status_label)
        
        info_label = QLabel("注意：当前为简化版，MT5连接已禁用")
        info_label.setStyleSheet("color: #FF9800; padding: 10px;")
        status_layout.addWidget(info_label)
        
        status_widget.setLayout(status_layout)
        main_layout.addWidget(status_widget)
        
        # 按钮
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        
        btn_connect = QPushButton("📡 连接MT5")
        btn_connect.setMinimumHeight(40)
        btn_connect.clicked.connect(self.connect_mt5)
        
        btn_start = QPushButton("▶ 启动自动交易")
        btn_start.setMinimumHeight(40)
        btn_start.clicked.connect(self.start_auto)
        
        btn_stop = QPushButton("⏸ 停止自动交易")
        btn_stop.setMinimumHeight(40)
        btn_stop.clicked.connect(self.stop_auto)
        
        buttons_layout.addWidget(btn_connect)
        buttons_layout.addWidget(btn_start)
        buttons_layout.addWidget(btn_stop)
        
        main_layout.addWidget(buttons_widget)
        
        # 日志区域
        log_widget = QGroupBox("系统日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        self.log_text.setStyleSheet("background: #1a1a2e; color: #e0e0e0; font-family: 'Consolas';")
        log_layout.addWidget(self.log_text)
        
        log_widget.setLayout(log_layout)
        main_layout.addWidget(log_widget)
        
        # 填充剩余空间
        main_layout.addStretch()
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        self.log("简化版面板启动成功")
        self.log("MT5连接当前禁用 - 如需真实交易请启动完整版")
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    def connect_mt5(self):
        self.log("MT5连接尝试 - 当前为简化版，真实连接已禁用")
        self.statusBar().showMessage("MT5连接: 模拟模式")
        
    def start_auto(self):
        self.log("自动交易启动 - 模拟模式")
        self.statusBar().showMessage("自动交易运行中 (模拟)")
        
    def stop_auto(self):
        self.log("自动交易停止")
        self.statusBar().showMessage("自动交易已停止")

if __name__ == "__main__":
    print("启动简化版BTC交易面板...")
    app = QApplication(sys.argv)
    window = SimpleBTCTradingPanel()
    window.show()
    print("窗口已显示，进入主循环...")
    sys.exit(app.exec())