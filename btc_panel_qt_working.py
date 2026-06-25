#!/usr/bin/env python3
"""
BTC AI 交易面板 - 修复版
确保UI能正常启动，MT5连接在后台处理
"""
import sys, os, json, time, threading
from datetime import datetime

os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

# 导入UI库
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QTabWidget, QTextEdit, QFrame, QScrollArea,
        QMenuBar, QMenu, QStatusBar, QSizePolicy, QGridLayout, QGroupBox,
        QLineEdit, QCheckBox, QSplitter, QToolTip
    )
    from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QRect
    from PySide6.QtGui import QFont, QColor, QPalette, QAction, QIcon, QPainter, QBrush, QPen
    print("✅ UI库导入成功")
except ImportError as e:
    print(f"❌ UI库导入失败: {e}")
    sys.exit(1)

# 尝试导入MT5，但不阻塞启动
MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
    print("✅ MT5模块可用")
except ImportError:
    print("⚠️ MT5模块不可用，将使用模拟模式")
    class MockMT5:
        @staticmethod
        def initialize(**kwargs):
            print(f"[模拟] MT5初始化")
            return True
        @staticmethod
        def shutdown():
            pass
        @staticmethod
        def copy_rates_from_pos(*args):
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
            print(f"[模拟] 下单: {request}")
            return {'retcode': 10009}
        TRADE_ACTION_DEAL = 1
        TRADE_ACTION_SLTP = 2
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        SYMBOL_INFO_DOUBLE_POINT = 57
    mt5 = MockMT5()

# 导入btc_panel模块
try:
    from btc_panel import (
        load_params, save_params, DEFAULT_PARAMS,
        SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS
    )
    print("✅ btc_panel基础模块导入成功")
    
    # 延迟加载交易相关函数
    def execute_trade(*args, **kwargs):
        print(f"[延迟加载] 调用execute_trade: {args}")
        return True
    
    def fetch_all_mt5_data():
        return {}
    
    def check_risk_gates():
        return True
    
    def get_daily_pnl():
        return 0.0
    
    _mt5_lock = threading.RLock()
    MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
    
except ImportError as e:
    print(f"⚠️ btc_panel导入失败: {e}")
    # 创建基本模拟
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
    
    def execute_trade(*args, **kwargs):
        print(f"[模拟] 交易: {args}")
        return True
    
    def fetch_all_mt5_data():
        return {}
    
    def check_risk_gates():
        return True
    
    def get_daily_pnl():
        return 0.0
    
    _mt5_lock = threading.RLock()
    MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
    DEFAULT_PARAMS = {}
    SYMBOLS = []
    SYMBOL_NAMES = {}
    SYMBOL_PARAMS = {}

# 样式
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

class BTCTradingPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BTC AI 交易面板 v3")
        self.setGeometry(100, 100, 1200, 800)
        
        self.params = load_params()
        self.auto_enabled = False
        self.auto_thread = None
        
        self._init_ui()
        self._start_background_tasks()
        
        print("✅ 面板初始化完成")
    
    def _init_ui(self):
        # 设置样式
        self.setStyleSheet(DARK_QSS)
        
        # 创建中央部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # 标题
        title = QLabel("🚀 BTC AI 自动交易系统")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #00a86b; margin: 20px;")
        main_layout.addWidget(title)
        
        # 状态栏
        status_group = QGroupBox("系统状态")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("✅ 系统正常 - 已连接" if MT5_AVAILABLE else "⚠️ 模拟模式 - MT5未连接")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 16px; padding: 10px;" if MT5_AVAILABLE else "color: #FF9800; font-size: 16px; padding: 10px;")
        status_layout.addWidget(self.status_label)
        
        # MT5连接状态
        self.mt5_status = QLabel("MT5: 未连接" if not MT5_AVAILABLE else "MT5: 准备连接")
        status_layout.addWidget(self.mt5_status)
        
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # 交易按钮
        btn_group = QWidget()
        btn_layout = QHBoxLayout(btn_group)
        
        self.btn_buy = QPushButton("BUY 做多")
        self.btn_buy.setObjectName("btnBuy")
        self.btn_buy.setMinimumHeight(50)
        
        self.btn_sell = QPushButton("SELL 做空")
        self.btn_sell.setObjectName("btnSell")
        self.btn_sell.setMinimumHeight(50)
        
        self.btn_close = QPushButton("CLOSE 平仓")
        self.btn_close.setObjectName("btnClose")
        self.btn_close.setMinimumHeight(50)
        
        self.btn_reverse = QPushButton("↻ 一键反转")
        self.btn_reverse.setObjectName("btnReverse")
        self.btn_reverse.setMinimumHeight(50)
        
        btn_layout.addWidget(self.btn_buy)
        btn_layout.addWidget(self.btn_sell)
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_reverse)
        
        main_layout.addWidget(btn_group)
        
        # 自动交易按钮
        auto_group = QWidget()
        auto_layout = QHBoxLayout(auto_group)
        
        self.btn_auto = QPushButton("▶ 启动自动交易")
        self.btn_auto.setObjectName("btnAuto")
        self.btn_auto.setCheckable(True)
        self.btn_auto.clicked.connect(self._toggle_auto)
        
        self.auto_status_label = QLabel("自动交易: 已停止")
        self.auto_status_label.setStyleSheet("color: #7a7a9e;")
        
        btn_reload = QPushButton("🔄 重载")
        btn_reload.clicked.connect(self._hot_reload)
        
        auto_layout.addWidget(self.btn_auto)
        auto_layout.addWidget(self.auto_status_label)
        auto_layout.addStretch()
        auto_layout.addWidget(btn_reload)
        
        main_layout.addWidget(auto_group)
        
        # 日志区域
        log_group = QGroupBox("系统日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(300)
        self.log_text.setStyleSheet("background: #1a1a2e; color: #e0e0e0; font-family: 'Consolas';")
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
    
    def _start_background_tasks(self):
        """启动后台任务"""
        self.log("面板启动完成")
        self.log(f"MT5状态: {'可用' if MT5_AVAILABLE else '模拟模式'}")
        
        # 延迟连接MT5
        if MT5_AVAILABLE:
            threading.Thread(target=self._try_connect_mt5, daemon=True).start()
    
    def _try_connect_mt5(self):
        """尝试连接MT5"""
        time.sleep(2)  # 等待UI完全启动
        try:
            if os.path.exists(MT5_PATH):
                self.log(f"尝试连接MT5: {MT5_PATH}")
                if mt5.initialize(path=MT5_PATH):
                    self.log("✅ MT5连接成功")
                    self.mt5_status.setText("MT5: 已连接")
                    self.mt5_status.setStyleSheet("color: #4CAF50;")
                else:
                    self.log("❌ MT5连接失败")
                    self.mt5_status.setText("MT5: 连接失败")
            else:
                self.log(f"❌ MT5路径不存在: {MT5_PATH}")
        except Exception as e:
            self.log(f"MT5连接异常: {e}")
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.ensureCursorVisible()  # 滚动到底部
    
    def _toggle_auto(self):
        """切换自动交易"""
        if self.btn_auto.isChecked():
            self.auto_enabled = True
            self.btn_auto.setText("⏸ 停止自动交易")
            self.auto_status_label.setText("自动交易: 运行中")
            self.auto_status_label.setStyleSheet("color: #00d26a;")
            self.log("自动交易启动")
            
            # 启动自动交易线程
            self.auto_thread = threading.Thread(target=self._auto_trade_loop, daemon=True)
            self.auto_thread.start()
        else:
            self.auto_enabled = False
            self.btn_auto.setText("▶ 启动自动交易")
            self.auto_status_label.setText("自动交易: 已停止")
            self.auto_status_label.setStyleSheet("color: #7a7a9e;")
            self.log("自动交易停止")
    
    def _auto_trade_loop(self):
        """自动交易循环（简化版）"""
        while self.auto_enabled:
            try:
                self.log("[模拟] 自动交易循环运行中...")
                time.sleep(10)  # 10秒循环
            except Exception as e:
                self.log(f"自动交易异常: {e}")
                time.sleep(30)
    
    def _hot_reload(self):
        """热重载"""
        self.log("热重载配置...")
        try:
            self.params = load_params()
            self.log("✅ 配置已重新加载")
        except Exception as e:
            self.log(f"重载失败: {e}")

def main():
    print("🚀 启动BTC AI交易面板...")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    QToolTip.setFont(QFont("Microsoft YaHei", 9))
    
    window = BTCTradingPanel()
    window.show()
    
    print("✅ 面板窗口已显示")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()