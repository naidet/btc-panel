#!/usr/bin/env python3
"""
BTC AI 交易面板 v3 - 修复启动问题版本
"""
import sys, os, json, time, threading
from datetime import datetime

os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")
sys.path.insert(0, r"C:\Users\82682\.workbuddy\binaries\python\envs\default\Lib\site-packages")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QTextEdit, QFrame, QScrollArea,
    QMenuBar, QMenu, QStatusBar, QSizePolicy, QGridLayout, QGroupBox,
    QLineEdit, QCheckBox, QSplitter, QToolTip
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QRect
from PySide6.QtGui import QFont, QColor, QPalette, QAction, QIcon, QPainter, QBrush, QPen

# 检查MT5是否存在，如果不存在则提供模拟版本
try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
    print("✅ MT5模块可用")
except ImportError:
    print("⚠️ MT5模块不可用，使用模拟模式")
    class MockMT5:
        @staticmethod
        def initialize(path=None, **kwargs):
            print(f"[模拟] MT5.initialize({path})")
            return True
        
        @staticmethod
        def shutdown():
            print(f"[模拟] MT5.shutdown()")
        
        @staticmethod
        def copy_rates_from_pos(symbol, timeframe, start_pos, count):
            print(f"[模拟] MT5.copy_rates_from_pos({symbol})")
            return []
        
        @staticmethod
        def account_info():
            return None
        
        @staticmethod
        def positions_total():
            return 0
        
        @staticmethod
        def positions_get(symbol=None):
            return []
        
        @staticmethod
        def order_send(request):
            print(f"[模拟] MT5.order_send({request})")
            return {'retcode': 10009}
        
        TRADE_ACTION_DEAL = 1
        TRADE_ACTION_SLTP = 2
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        SYMBOL_INFO_DOUBLE_POINT = 57
    
    mt5 = MockMT5()
    HAS_MT5 = False

# 导入btc_panel模块，处理可能的导入错误
try:
    from btc_panel import (
        execute_trade, fetch_all_mt5_data, check_risk_gates, get_daily_pnl,
        _mt5_lock, MT5_PATH, DEFAULT_PARAMS, load_params, save_params,
        SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS
    )
    print("✅ btc_panel模块导入成功")
except ImportError as e:
    print(f"⚠️ btc_panel导入失败: {e}")
    # 创建模拟函数
    class MockBTCPanel:
        _mt5_lock = threading.RLock()
        MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
        DEFAULT_PARAMS = {}
        SYMBOLS = []
        SYMBOL_NAMES = {}
        SYMBOL_PARAMS = {}
    
    def load_params():
        try:
            return json.load(open("panel_params.json")) if os.path.exists("panel_params.json") else {}
        except:
            return {}
    
    def save_params(params):
        try:
            json.dump(params, open("panel_params.json", "w"), indent=2)
        except:
            pass
    
    def execute_trade(action, symbol, **kwargs):
        print(f"[模拟交易] {action} {symbol}")
        return True
    
    def fetch_all_mt5_data():
        return {}
    
    def check_risk_gates():
        return True
    
    def get_daily_pnl():
        return 0.0
    
    _mt5_lock = MockBTCPanel._mt5_lock
    MT5_PATH = MockBTCPanel.MT5_PATH
    DEFAULT_PARAMS = MockBTCPanel.DEFAULT_PARAMS
    SYMBOLS = MockBTCPanel.SYMBOLS
    SYMBOL_NAMES = MockBTCPanel.SYMBOL_NAMES
    SYMBOL_PARAMS = MockBTCPanel.SYMBOL_PARAMS

# QSS样式
DARK_QSS = """
QMainWindow { background: #0d0d1a; }
QWidget { background: #0d0d1a; color: #e0e0e0; font-family: "Microsoft YaHei"; font-size: 13px; }
QMenuBar { background: #15152a; color: #e0e0e0; border-bottom: 1px solid #222244; font-size: 13px; }
QMenuBar::item:selected { background: #252550; }
QMenu { background: #15152a; color: #e0e0e0; border: 1px solid #333366; font-size: 13px; }
QMenu::item:selected { background: #252550; }
QTabWidget::pane { border: 1px solid #222244; background: #0d0d1a; }
QTabBar::tab { background: #15152a; color: #7a7a9e; padding: 10px 24px; border: none; font-size: 14px; font-weight: bold; }
QTabBar::tab:selected { background: #00a86b; color: white; }
QTabBar::tab:hover { background: #252550; color: #e0e0e0; }
QPushButton { border-radius: 4px; padding: 10px 20px; font-weight: bold; font-size: 14px; }
QPushButton#btnBuy { background: #2a2a3a; color: #5a5a7a; border: 1px solid #333355; }
QPushButton#btnBuy[active="true"] { background: #00a86b; color: white; border: none; }
QPushButton#btnSell { background: #2a2a3a; color: #5a5a7a; border: 1px solid #333355; }
QPushButton#btnSell[active="true"] { background: #ff4d6a; color: white; border: none; }
QPushButton#btnClose { background: #2a2a3a; color: #5a5a7a; border: 1px solid #333355; }
QPushButton#btnClose[active="true"] { background: #ffc107; color: #1a1a2e; border: none; }
QPushButton#btnReverse { background: #2a2a3a; color: #5a5a7a; border: 1px solid #333355; }
QPushButton#btnReverse[active="true"] { background: #ffc107; color: #1a1a2e; border: none; }
QPushButton#btnAuto { background: #252540; color: #00d26a; border: 1px solid #00a86b; font-size: 13px; }
"""

# 以下是原始代码的其余部分，但由于长度限制，我将保存完整的修复版本...

# 我将在下一步创建完整的修复版本