#!/usr/bin/env python3
"""
BTC AI 交易面板 v3 - PySide6 专业桌面版
黄金 & BTC 量化交易面板
"""
import sys, os, json, time, threading, traceback, socket
from datetime import datetime, timedelta

# ═══════════════════════════════════════════
# 全局异常捕获 (noconsole EXE不会显示黑窗, 错误写日志)
# ═══════════════════════════════════════════
def _log_crash(exc_type, exc_val, exc_tb):
    log_path = os.path.join(os.path.dirname(sys.executable), "btc_panel_crash.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] FATAL CRASH\n")
            f.write(f"  Type: {exc_type.__name__}: {exc_val}\n")
            f.write(f"  Traceback:\n")
            traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
    except:
        pass
    sys.__excepthook__(exc_type, exc_val, exc_tb)
sys.excepthook = _log_crash

# ═══════════════════════════════════════════
# 路径兼容: 开发环境 vs PyInstaller EXE
# ═══════════════════════════════════════════
if getattr(sys, 'frozen', False):
    # PyInstaller onefile 模式
    _APP_DIR = sys._MEIPASS
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
    try:
        os.chdir(_APP_DIR)
    except:
        pass
sys.path.insert(0, _APP_DIR)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QTextEdit, QFrame, QScrollArea,
    QMenuBar, QMenu, QStatusBar, QSizePolicy, QGridLayout, QGroupBox,
    QLineEdit, QCheckBox, QSplitter, QToolTip
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QRect
from PySide6.QtGui import QFont, QColor, QPalette, QAction, QIcon, QPainter, QBrush, QPen

from btc_panel import (
    execute_trade, fetch_all_mt5_data, fetch_dashboard_data, check_risk_gates, get_daily_pnl,
    get_mt5_tick, get_mt5_positions, get_mt5_account_info, update_hmm_state, get_trade_signal,
    _mt5_lock, MT5_PATH, DEFAULT_PARAMS, load_params, save_params, modify_sl, _load_symbol_params,
    mt5_reconnect, check_autotrading,
    SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS,
    is_trade_time_allowed, auto_setup_broker, _broker_info,
    _real_symbol, _ensure_symbols_ready,
)
import MetaTrader5 as mt5
from license import check_license, show_license_dialog, get_hwid
from updater import check_update as check_update_remote, download_update, apply_update, CURRENT_VERSION

# QSS
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
QPushButton#btnAuto:checked { background: #00a86b; color: white; }
QGroupBox { border: 1px solid #222244; border-radius: 6px; margin-top: 12px; padding-top: 10px; color: #4dabf7; font-size: 14px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; }
QLineEdit { background: #15152a; border: 1px solid #333366; border-radius: 3px; padding: 6px 8px; color: #e0e0e0; font-size: 14px; }
QTextEdit { background: #0a0a18; border: 1px solid #222244; border-radius: 4px; color: #b0b0cc; font-family: "Consolas"; font-size: 12px; }
QScrollBar:vertical { background: #0d0d1a; width: 8px; }
QScrollBar::handle:vertical { background: #333366; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #0a0a18; color: #c0c0cc; border-top: 2px solid #333366; font-size: 13px; min-height: 28px; }
QLabel#priceBig { font-size: 44px; font-weight: bold; color: white; }
"""

GREEN  = "#00d26a"
RED    = "#ff4d6a"
BLUE   = "#4dabf7"
YELLOW = "#ffc107"
GRAY   = "#7a7a9e"
WHITE  = "#ffffff"
CARD   = "#15152a"
BG     = "#0d0d1a"

class UISignals(QObject):
    log_msg = Signal(str)
    update_ui = Signal(dict, dict, list, dict)
    update_risk = Signal(dict)
    auto_status = Signal(bool)
    update_available = Signal(dict)  # 发现新版本, 携带 update_info
    dl_progress = Signal(int, int, int)  # 下载进度: pct, downloaded, total

class MiniBar(QWidget):
    def __init__(self, color_hint="#555555"):
        super().__init__()
        self._pct = 0; self._color = QColor(color_hint)
        self.setMinimumSize(120, 22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    def set_value(self, pct: float, color: str):
        self._pct = max(0, min(100, pct)); self._color = QColor(color); self.update()
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen); p.setBrush(QColor("#1a1a35"))
        p.drawRoundedRect(0, 0, w, h, 2, 2)
        fill_w = int(self._pct / 100 * w)
        if fill_w > 1:
            p.setBrush(self._color); p.drawRoundedRect(0, 0, fill_w, h, 2, 2)
        if self._pct > 5:
            p.setPen(QColor("#ffffff")); p.setFont(QFont("Consolas", 9, QFont.Bold))
            p.drawText(0, 0, w, h, Qt.AlignCenter, f"{self._pct:.0f}%")
        p.end()

class SignalBar(QWidget):
    def __init__(self):
        super().__init__(); self._pct = 0; self._color = QColor("#555555"); self._text = ""
        self.setMinimumSize(100, 32)
    def set_value(self, pct: float, color: str, text: str):
        self._pct = pct; self._color = QColor(color); self._text = text; self.update()
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); mid = w // 2
        p.setPen(Qt.NoPen); p.setBrush(QColor("#0d0d1a"))
        p.drawRoundedRect(0, 0, w, h, 4, 4)
        p.setPen(QColor("#333355")); p.drawLine(mid, 0, mid, h)
        abs_pct = abs(self._pct); fill_w = int(abs_pct / 100 * mid)
        if fill_w > 2:
            x0, x1 = (mid, mid + fill_w) if self._pct > 0 else (mid - fill_w, mid)
            p.setPen(Qt.NoPen); p.setBrush(self._color)
            p.drawRoundedRect(x0, 3, x1 - x0, h - 6, 3, 3)
        if self._text:
            p.setPen(QColor("#ffffff")); p.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
            if abs_pct > 5:
                if self._pct > 0: p.drawText(mid + 6, 0, fill_w - 10, h, Qt.AlignCenter, self._text)
                else: p.drawText(x0, 0, fill_w - 4, h, Qt.AlignCenter, self._text)
        p.end()

# ═══════════════════ MainWindow ═══════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"BTC Panel v{CURRENT_VERSION}")
        self.setMinimumSize(800, 950); self.resize(850, 980)
        self.setStyleSheet(DARK_QSS)
        # 悬浮模式: 半透明 + 不置顶(默认)
        self._overlay_opacity = 1.0  # 默认不透明, 用户可在 窗口→透明度 中调整
        self._always_on_top = False
        self.setWindowOpacity(self._overlay_opacity)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        # 恢复拖拽焦点: 确保窗口可交互
        self.setAttribute(Qt.WA_TranslucentBackground, False)  # 不启用真透明, 用opacity控制
        self.symbol = "XAUUSD"
        self.params = load_params(self.symbol)
        self.auto_enabled = False
        self._has_position = False; self._position_side = None
        self._fetch_busy = False; self._binance_ok = False
        self._cached_data = {}; self._cached_ml = {}; self._cached_resonance = []
        self._cached_filter_info = {}
        self._resonance_fail_count = 0
        self._hmm_state = {"state": -1, "label": "加载中...", "confidence": 0}
        self._last_hmm_log = ""
        self._hmm_symbols = {"XAUUSD", "BTCUSD"}
        self._update_info = None        # 更新信息缓存
        self._pending_update = None     # 跨线程更新标志 (主线程轮询)
        self._update_poll_timer = QTimer(self)
        self._update_poll_timer.timeout.connect(self._poll_update)
        self._update_poll_timer.start(1000)  # 每秒轮询
        self.signals = UISignals()
        self.signals.log_msg.connect(self._on_log)
        self.signals.update_ui.connect(self._update_ui)
        self.signals.update_available.connect(self._prompt_update)  # 主线程序安全
        self.signals.update_risk.connect(self._update_risk_status)
        self._setup_menubar()
        self._setup_ui()
        self._setup_statusbar()
        self._init_tooltips()  # 所有名词解释
        self._delayed_init()

        # 启动横幅
        self.log("╔══════════════════════════════════════════════╗")
        self.log("║  BTC Panel v3                              ║")
        self.log("║  多周期共振 + ML引擎 + HMM状态 + 风控系统   ║")
        self.log("╚══════════════════════════════════════════════╝")
        self.log(f"⚙️ 当前品种: {SYMBOL_NAMES.get(self.symbol, self.symbol)} ({self.symbol})")
        self.log(f"⚙️ 刷新间隔: 60秒 | 自动交易: 未启动")
        # 授权信息
        lic = getattr(self, "_license_info", None) or {}
        if lic.get("trial"):
            self.log(f"🔑 试用授权 — 剩余 {lic.get('trial_left','?')} 天 | 到期: {lic.get('expiry','?')}")
        elif lic.get("valid"):
            self.log(f"🔑 已激活 — 到期: {lic.get('expiry','?')} | 机器: {lic.get('hwid','?')}")
        self.log("🚀 系统就绪 — 正在连接券商...")

    def _setup_menubar(self):
        mb = self.menuBar()
        f=mb.addMenu("文件(&F)"); f.addAction("保存参数", self._apply_params)
        f.addAction("重置参数", self._reset_params); f.addSeparator()
        f.addAction("退出(&X)", self.close)
        v=mb.addMenu("视图(&V)")
        v.addAction("显示日志", lambda: self.log_area.setVisible(True))
        v.addAction("隐藏日志", lambda: self.log_area.setVisible(False))
        # 窗口悬浮控制
        w=mb.addMenu("窗口(&W)")
        self._top_action = w.addAction("📌 置顶显示")
        self._top_action.setCheckable(True)
        self._top_action.setChecked(False)
        self._top_action.triggered.connect(self._toggle_ontop)
        op_menu = w.addMenu("透明度")
        for pct, label in [(0.95,"95% 几乎不透明"),(0.88,"88% 默认"),(0.75,"75%"),(0.60,"60% 半透明"),(0.45,"45% 高度透明")]:
            a = op_menu.addAction(label)
            a.setData(pct)
            a.triggered.connect(lambda checked, v=pct: self._set_opacity(v))
        t=mb.addMenu("工具(&T)")
        t.addAction("🔍 重新连接券商", self._connect_broker)
        t.addAction("🔄 检查更新", self._check_update)
        mb.addMenu("帮助(&H)").addAction("关于", self._about)

    def _toggle_ontop(self, checked: bool):
        self._always_on_top = checked
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()  # 必须重新show才能应用windowFlags变更
        status = "✅ 已置顶" if checked else "◻ 已取消置顶"
        self._top_action.setChecked(checked)
        self.log(status)

    def _toggle_detail(self):
        """收起/展开详情区, 隐藏时释放空间"""
        vis = not self.detail_frame.isVisible()
        self.detail_frame.setVisible(vis)
        if vis:
            self.detail_frame.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        else:
            self.detail_frame.setMaximumHeight(0)
        self.detail_btn.setText("▲ 收起详情" if vis else "▼ 查看详情")

    def _toggle_param(self):
        """收起/展开参数区, 隐藏时释放空间"""
        vis = not self.param_group.isVisible()
        self.param_group.setVisible(vis)
        if vis:
            self.param_group.setMaximumHeight(16777215)
        else:
            self.param_group.setMaximumHeight(0)
        self.param_toggle.setText("▲ 收起参数" if vis else "⚙ 参数设置 ▼")

    def _set_opacity(self, value: float):
        self._overlay_opacity = value
        self.setWindowOpacity(value)
        self.log(f"🔍 面板透明度: {int(value*100)}%")

    def _setup_statusbar(self):
        # 状态栏简化为纯风险/版本信息
        self.sb = QStatusBar(); self.setStatusBar(self.sb)
        self.sb_risk = QLabel("日: $0  回撤: 0%"); self.sb_ver = QLabel("v3.0 PySide6")
        self.sb.addPermanentWidget(self.sb_risk)
        self.sb.addPermanentWidget(self.sb_ver)

    def _update_license_label(self, lic: dict):
        """更新授权小标签"""
        if not lic:
            self.lic_banner.hide()
            return
        if lic.get("trial"):
            left = lic.get("trial_left", 0)
            exp = lic.get("expiry", "?")
            if left > 1:
                self.lic_banner.setText(f"试用 {left}天 | {exp}")
                self.lic_banner.setStyleSheet("font-size: 11px; padding: 2px 10px; border-radius: 8px; color: #ffc107; background: #2a2200; border: 1px solid #553300;")
            elif left == 1:
                self.lic_banner.setText(f"最后1天!")
                self.lic_banner.setStyleSheet("font-size: 11px; padding: 2px 10px; border-radius: 8px; color: #ff6b6b; background: #2a0000; border: 1px solid #552222;")
            else:
                self.lic_banner.setText(f"已到期")
                self.lic_banner.setStyleSheet("font-size: 11px; padding: 2px 10px; border-radius: 8px; color: #ff4d6a; background: #2a0000; border: 1px solid #552222;")
            self.lic_banner.show()
        elif lic.get("valid"):
            exp = lic.get("expiry", "?")
            self.lic_banner.setText(f"v3 | {exp}")
            self.lic_banner.setStyleSheet("font-size: 10px; padding: 2px 8px; border-radius: 8px; color: #447744; background: #0a1a0a; border: 1px solid #224422;")
            self.lic_banner.show()
        elif lic.get("expired"):
            self.lic_banner.setText(f"已过期")
            self.lic_banner.setStyleSheet("font-size: 11px; padding: 2px 10px; border-radius: 8px; color: #ff4d6a; background: #2a0000; border: 1px solid #552222;")
            self.lic_banner.show()
        else:
            self.lic_banner.setText("未激活")
            self.lic_banner.setStyleSheet("font-size: 11px; padding: 2px 10px; border-radius: 8px; color: #ff4d6a; background: #2a0000; border: 1px solid #552222;")
            self.lic_banner.show()

    def _setup_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0d0d1a; }")
        content = QWidget()
        ml = QVBoxLayout(content); ml.setContentsMargins(16,12,16,12); ml.setSpacing(10)

        self._build_category_selector(ml)

        self.price_frame = self._make_card("实时价格")
        self.price_big = QLabel("$ ------"); self.price_big.setObjectName("priceBig")
        self.price_big.setAlignment(Qt.AlignCenter)
        self.price_sub = QLabel("Bid: ------  Ask: ------")
        self.price_sub.setAlignment(Qt.AlignCenter)
        self.price_sub.setStyleSheet("color: #7a7a9e; font-size: 13px;")
        self.price_frame.layout().addWidget(self.price_big)
        self.price_frame.layout().addWidget(self.price_sub)
        ml.addWidget(self.price_frame)

        pr = QHBoxLayout()
        self.pos_frame = self._make_card("持仓")
        self.pos_side = QLabel("空仓"); self.pos_side.setStyleSheet("font-size: 22px; font-weight: bold; color: #7a7a9e;")
        self.pos_detail = QLabel("无当前持仓"); self.pos_detail.setStyleSheet("color: #7a7a9e; font-size: 16px;")
        self.pos_frame.layout().addWidget(self.pos_side)
        self.pos_frame.layout().addWidget(self.pos_detail)
        pr.addWidget(self.pos_frame, 3)
        self.bal_frame = self._make_card("账户")
        self.broker_label = QLabel("券商: ------"); self.broker_label.setStyleSheet("color: #ffc107; font-size: 13px; font-weight: bold;")
        self.login_label = QLabel("账号: ------"); self.login_label.setStyleSheet("color: #9a9ac0; font-size: 13px;")
        self.bal_label = QLabel("余额: ------"); self.equity_label = QLabel("净值: ------")
        for w in [self.broker_label,self.login_label,self.bal_label,self.equity_label]:
            self.bal_frame.layout().addWidget(w)
        pr.addWidget(self.bal_frame, 2); ml.addLayout(pr)

        # 合并版信号卡 (实时信号 + 主信号 + HMM)
        sig_card = self._make_card("实时信号")
        slayout = sig_card.layout()   # 复用_make_card创建好的layout，不要再新建！
        slayout.setSpacing(8); slayout.setContentsMargins(12,10,12,10)

        # 第一行: 大号主信号 + HMM标签
        sig_row1 = QHBoxLayout(); sig_row1.setSpacing(10)
        self.main_signal_icon = QLabel("◆")
        self.main_signal_icon.setStyleSheet("font-size: 24px; font-weight: bold; color: #e0e0e0;")
        self.main_signal_icon.setMinimumSize(30, 28)  # 保证有渲染区域
        sig_row1.addWidget(self.main_signal_icon)
        self.sig_label = QLabel("等待数据...")
        self.sig_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #7a7a9e;")
        self.sig_label.setMinimumHeight(28)  # 保证有渲染区域
        sig_row1.addWidget(self.sig_label, 1)
        
        # HMM标签 (右边显示)
        self.hmm_label = QLabel("HMM: 加载中...")
        self.hmm_label.setStyleSheet("color: #c0c0cc; font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #2a2a44;")
        self.hmm_label.setMinimumHeight(22)
        sig_row1.addWidget(self.hmm_label)
        slayout.addLayout(sig_row1)

        # 新增: 多空力量比例条 (真正的动态条,不是文字)
        self.prop_container = QWidget()
        self.prop_container.setMinimumHeight(36)
        prop_layout = QHBoxLayout(self.prop_container)
        prop_layout.setContentsMargins(0, 0, 0, 0); prop_layout.setSpacing(4)
        # 左边: 做多百分比
        self.buy_label = QLabel("做多 50%")
        self.buy_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.buy_label.setStyleSheet("color: #00d26a; font-size: 12px; font-weight: bold; min-width: 60px;")
        prop_layout.addWidget(self.buy_label)
        # 中间: 动态比例条
        self.bar_container = QWidget()
        self.bar_container.setStyleSheet("background: #1a1a33; border-radius: 6px; border: 1px solid #333355;")
        bar_inner = QHBoxLayout(self.bar_container)
        bar_inner.setContentsMargins(0, 0, 0, 0); bar_inner.setSpacing(0)
        self.buy_bar = QFrame()
        self.buy_bar.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b84c, stop:1 #00e66a); border-radius: 6px; min-height: 18px;")
        self.buy_bar.setMinimumSize(4, 22)
        self.sell_bar = QFrame()
        self.sell_bar.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e63333, stop:1 #cc1111); border-radius: 6px; min-height: 18px;")
        self.sell_bar.setMinimumSize(4, 22)
        bar_inner.addWidget(self.buy_bar, 5)
        bar_inner.addWidget(self.sell_bar, 5)
        prop_layout.addWidget(self.bar_container, 1)
        # 右边: 做空百分比
        self.sell_label = QLabel("做空 50%")
        self.sell_label.setStyleSheet("color: #cc2222; font-size: 12px; font-weight: bold; min-width: 60px;")
        prop_layout.addWidget(self.sell_label)
        slayout.addWidget(self.prop_container)

        # 第二行: 信号条 + HMM信息
        sig_row2 = QHBoxLayout(); sig_row2.setSpacing(8)
        self.sig_bar = SignalBar()
        self.sig_bar.setMinimumSize(120, 28)   # 保证有渲染区域
        sig_row2.addWidget(self.sig_bar, 1)
        self.hmm_conf = QLabel("")
        self.hmm_conf.setStyleSheet("color: #7a7a9e; font-size: 11px; padding: 2px 8px;")
        self.hmm_conf.setMinimumHeight(20)
        sig_row2.addWidget(self.hmm_conf)
        slayout.addLayout(sig_row2)

        # 第三行: 共振/引擎/组信号信息
        self.sig_text = QLabel("等待数据刷新...")
        self.sig_text.setStyleSheet("color: #7a7a9e; font-size: 13px;")
        self.sig_text.setMinimumHeight(18)
        slayout.addWidget(self.sig_text)
        
        # 第四行: 主信号详细理由 (小号灰色)
        self.main_signal_reason = QLabel("")
        self.main_signal_reason.setStyleSheet("color: #7a7a9e; font-size: 11px; padding: 0px 4px;")
        self.main_signal_reason.setMinimumHeight(16)
        self.main_signal_reason.setWordWrap(True)   # 允许换行
        slayout.addWidget(self.main_signal_reason)

        # 添加弹性空间，确保信号卡有足够高度
        slayout.addStretch(0)

        ml.addWidget(sig_card)
        self.sig_frame = sig_card

        # 合并到实时信号卡中，移除冗余主信号区域
        # 实时信号卡增加主信号信息显示
        # ...

        self.detail_frame = QFrame(); self.detail_frame.setVisible(False)
        self.detail_frame.setStyleSheet(f"background: {CARD}; border-radius: 6px; padding: 10px;")
        dl = QVBoxLayout(self.detail_frame); dl.setSpacing(5)
        self.detail_rows = {}
        for label, color in [("核心引擎","#ffd700"),("脉冲层","#00e5ff"),("谐波段","#a855f7"),("基频面","#ff6b6b")]:
            row = QHBoxLayout()
            nl = QLabel(label); nl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;"); nl.setMinimumWidth(60)
            row.addWidget(nl)
            dw = QLabel("---"); dw.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 12px;"); dw.setMinimumWidth(55)
            row.addWidget(dw)
            dp = QLabel("--"); dp.setStyleSheet("color: #cccccc; font-size: 11px;"); dp.setMinimumWidth(50)
            row.addWidget(dp)
            bar = MiniBar(color); row.addWidget(bar, 1); row.addStretch()
            dl.addLayout(row); self.detail_rows[label] = (dw, dp, bar)
        ml.addWidget(self.detail_frame)
        bt = QPushButton("▼ 查看详情"); bt.setStyleSheet("background: #222244; color: #00e5ff; border: none; font-size: 13px; padding: 6px;")
        bt.clicked.connect(lambda: self._toggle_detail())
        ml.addWidget(bt)
        self.detail_btn = bt  # 保存引用

        # 参数面板 (简化版: 只暴露用户友好参数, 高级参数硬编码最优值)
        self.param_group = self._make_card("策略参数"); self.param_widgets = {}
        def ap(rl, lt, k, w=50):
            lb = QLabel(lt); lb.setStyleSheet("color: #7a7a9e; font-size: 13px;")
            ed = QLineEdit(str(self.params.get(k, DEFAULT_PARAMS.get(k,""))))
            ed.setFixedWidth(w); ed.setStyleSheet("padding: 4px 6px; font-size: 14px;")
            rl.addWidget(lb); rl.addWidget(ed); self.param_widgets[k] = ed
        r1 = QHBoxLayout()
        for kk in [("lot_fixed","固定手数",45),("risk_per_trade","风险$",45),("trail_profit","追$",55),("cooldown_minutes","冷却m",45)]:
            ap(r1, kk[1], kk[0], kk[2] if len(kk)>2 else 50)
        r1.addStretch(); self.param_group.layout().addLayout(r1)
        r2 = QHBoxLayout()
        for kk in [("profit_lock_trigger","盈利锁$",50),("profit_lock_pullback","利润回落%",55),("max_daily_loss","日亏≤$",55),("max_drawdown_pct","回撤≤%",45)]:
            ap(r2, kk[1], kk[0], kk[2] if len(kk)>2 else 50)
        r2.addStretch(); self.param_group.layout().addLayout(r2)
        br = QHBoxLayout()
        ba = QPushButton("应用"); ba.setStyleSheet("background: #00a86b; color: white; padding: 4px 16px; font-weight: bold;"); ba.clicked.connect(self._apply_params)
        br.addWidget(ba)
        bt2 = QPushButton("重置"); bt2.setStyleSheet("background: #333366; color: #7a7a9e; padding: 4px 16px;"); bt2.clicked.connect(self._reset_params)
        br.addWidget(bt2); br.addStretch(); self.param_group.layout().addLayout(br)
        self.param_group.setVisible(False)
        self.param_toggle = QPushButton("⚙ 参数设置 ▼"); self.param_toggle.setStyleSheet("background: #15152a; color: #4dabf7; border: none; font-size: 13px; padding: 5px;")
        self.param_toggle.clicked.connect(lambda: self._toggle_param())
        ml.addWidget(self.param_toggle); ml.addWidget(self.param_group)

        btn_frame = QHBoxLayout()
        self.btn_buy = QPushButton("📈 做多 (BUY)"); self.btn_buy.setObjectName("btnBuy"); self.btn_buy.setMinimumHeight(40)
        self.btn_buy.clicked.connect(lambda: self._on_trade("BUY"))
        self.btn_close = QPushButton("📊 平仓 (CLOSE)"); self.btn_close.setObjectName("btnClose"); self.btn_close.setMinimumHeight(40)
        self.btn_close.clicked.connect(lambda: self._on_trade("CLOSE"))
        self.btn_sell = QPushButton("📉 做空 (SELL)"); self.btn_sell.setObjectName("btnSell"); self.btn_sell.setMinimumHeight(40)
        self.btn_sell.clicked.connect(lambda: self._on_trade("SELL"))
        self.btn_reverse = QPushButton("🔄 一键反转"); self.btn_reverse.setObjectName("btnReverse")
        self.btn_reverse.setStyleSheet("background: #252540; color: #ffc107; font-weight: bold; border-radius: 4px;"); self.btn_reverse.setMinimumHeight(40)
        self.btn_reverse.clicked.connect(self._on_reverse)
        btn_frame.addWidget(self.btn_buy); btn_frame.addWidget(self.btn_close)
        btn_frame.addWidget(self.btn_sell); btn_frame.addWidget(self.btn_reverse); ml.addLayout(btn_frame)

        ar = QHBoxLayout()
        self.btn_auto = QPushButton("▶ 启动自动交易"); self.btn_auto.setObjectName("btnAuto"); self.btn_auto.setCheckable(True)
        self.btn_auto.clicked.connect(self._toggle_auto); ar.addWidget(self.btn_auto)
        self.auto_status_label = QLabel("自动交易: 已停止"); self.auto_status_label.setStyleSheet("color: #7a7a9e;")
        ar.addWidget(self.auto_status_label)
        btn_reload = QPushButton("🔄 重载"); btn_reload.setToolTip("从文件重新加载参数+热重载修改的模块")
        btn_reload.setStyleSheet("background: #252540; color: #4dabf7; border: 1px solid #333366; padding: 3px 8px; font-size: 11px;")
        btn_reload.clicked.connect(self._hot_reload); ar.addWidget(btn_reload)
        ar.addStretch(); ml.addLayout(ar)

        self.log_area = QTextEdit(); self.log_area.setReadOnly(True); self.log_area.setMinimumHeight(100)
        self.log_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ml.addWidget(self.log_area, 1)

        content.setLayout(ml); scroll.setWidget(content); root.addWidget(scroll)

    def _make_card(self, title):
        gb = QGroupBox(title); gb.setLayout(QVBoxLayout())
        gb.layout().setContentsMargins(12,8,12,8); gb.layout().setSpacing(6)
        return gb

    def _build_category_selector(self, parent_layout):
        # 品类映射 — 面板仅支持黄金和BTC
        ALL_CATEGORIES = {
            "🥇 黄金":   ["XAUUSD"],
            "🪙 BTC":    ["BTCUSD"],
        }
        # 只保留当前券商可用的品种
        CATEGORIES = {}
        for cat, syms in ALL_CATEGORIES.items():
            available = [s for s in syms if s in SYMBOLS]
            if available:
                CATEGORIES[cat] = available
        self._cat_map = CATEGORIES
        bar = QHBoxLayout(); bar.setSpacing(6)
        self._sel_label = QLabel("📋 选择产品:"); self._sel_label.setStyleSheet("color: #7a7a9e; font-size: 12px;")
        bar.addWidget(self._sel_label)
        init_sym = self.symbol; init_name = SYMBOL_NAMES.get(init_sym, init_sym)
        init_cat = ""
        for cat, syms in CATEGORIES.items():
            if init_sym in syms: init_cat = cat; break
        btn_text = f"{init_cat} > {init_name} {init_sym} ▾" if init_cat else f"{init_name} {init_sym} ▾"
        self._sel_btn = QPushButton(btn_text)
        self._sel_btn.setStyleSheet("""
            QPushButton { background: #15152a; color: #00d26a; border: 1px solid #333366;
            border-radius: 4px; padding: 4px 12px; font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #1e1e3a; }
        """)
        self._sel_btn.setCursor(Qt.PointingHandCursor)
        self._sel_btn.clicked.connect(self._show_symbol_menu)
        self._sel_btn.setToolTip("点击展开品类菜单选择交易品种")
        bar.addWidget(self._sel_btn)
        # —— MT5连接状态 (醒目, 放在选择栏) ——
        self.mt5_status_led = QLabel("○ 等待连接")
        self.mt5_status_led.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 8px; color: #7a7a9e; background: #15152a; border: 1px solid #333366;")
        bar.addWidget(self.mt5_status_led)
        # 授权小标签
        self.lic_banner = QLabel("")
        self.lic_banner.setStyleSheet("font-size: 10px; padding: 2px 8px; border-radius: 8px;")
        bar.addWidget(self.lic_banner)
        bar.addStretch()
        # 版本号
        self.ver_label = QLabel(f"v{CURRENT_VERSION}")
        self.ver_label.setStyleSheet("font-size: 10px; padding: 2px 8px; border-radius: 8px; color: #5a5a8a; background: #0d0d1a;")
        self.ver_label.setCursor(Qt.PointingHandCursor)
        self.ver_label.setToolTip(f"BTC Panel v{CURRENT_VERSION} — 点击检查更新")
        self.ver_label.mousePressEvent = lambda e: self._check_update()
        bar.addWidget(self.ver_label)
        parent_layout.addLayout(bar)

    def _show_symbol_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #15152a; color: #e0e0e0; border: 1px solid #333366; padding: 4px; }
            QMenu::item { padding: 6px 24px 6px 12px; font-size: 12px; }
            QMenu::item:selected { background: #252550; }
            QMenu::separator { height: 1px; background: #222244; margin: 2px 8px; }
        """)
        for cat_name, symbols in self._cat_map.items():
            cm = menu.addMenu(cat_name); cm.setStyleSheet(menu.styleSheet())
            for sym in symbols:
                name = SYMBOL_NAMES.get(sym, sym)
                a = cm.addAction(f"  {name}  ({sym})")
                a.triggered.connect(lambda checked, s=sym: self._on_menu_select(s))
            if cat_name != list(self._cat_map.keys())[-1]: menu.addSeparator()
        menu.exec_(self._sel_btn.mapToGlobal(self._sel_btn.rect().bottomLeft()))

    def _on_menu_select(self, sym):
        if sym == self.symbol: return
        for cat, syms in self._cat_map.items():
            if sym in syms:
                name = SYMBOL_NAMES.get(sym, sym)
                self._sel_btn.setText(f"{cat} > {name} {sym} ▾")
                break
        self.switch_symbol(sym)

    def switch_symbol(self, new_sym):
        if new_sym == self.symbol: return
        old = self.symbol; self.symbol = new_sym; self._last_hmm_log = ""
        # 加载新品种的参数文件 (品种独立)
        self.params = load_params(new_sym)
        # 合入品种配置中的默认值
        sp = SYMBOL_PARAMS.get(new_sym, {})
        for k, v in sp.items(): self.params.setdefault(k, v)
        # 刷新UI参数控件
        for k, w in self.param_widgets.items():
            w.setText(str(self.params.get(k, DEFAULT_PARAMS.get(k, ""))))
        self.price_big.setText("$ ------"); self.price_sub.setText("切换中...")
        self.pos_side.setText("空仓"); self.pos_detail.setText("切换中...")
        name = SYMBOL_NAMES.get(new_sym, new_sym)
        for cat, syms in self._cat_map.items():
            if new_sym in syms:
                self._sel_btn.setText(f"{cat} > {name} {new_sym} ▾"); break
        self.log(f"切换: {SYMBOL_NAMES.get(old,old)} -> {name}")
        self._trigger_fetch()

    def log(self, msg): self.signals.log_msg.emit(msg)

    def _on_log(self, msg):
        ts = datetime.now().strftime("[%H:%M:%S]")
        self.log_area.append(f"{ts} {msg}")
        sb = self.log_area.verticalScrollBar(); sb.setValue(sb.maximum())
    def _on_trade(self, action):
        def _threaded():
            self.log(f"⏳ 正在执行: {action} ...")
            try: result = execute_trade(action, self.symbol)
            except Exception as e: result = f"异常: {e}"
            self.signals.log_msg.emit(f"💰 结果: {result}")
            time.sleep(1); self._trigger_fetch()
        threading.Thread(target=_threaded, daemon=True).start()

    def _on_reverse(self):
        if not self._position_side: self.log("反转: 无持仓"); return
        rev = "SELL" if self._position_side == "多" else "BUY"
        self.log(f"一键反转: 平{self._position_side} -> 开{'空' if rev=='SELL' else '多'}")
        threading.Thread(target=lambda: (execute_trade("CLOSE",self.symbol), time.sleep(2), execute_trade(rev,self.symbol)), daemon=True).start()

    def _toggle_auto(self):
        self.auto_enabled = not self.auto_enabled
        if self.auto_enabled:
            self.btn_auto.setText("⏸ 停止自动交易")
            self.btn_auto.setStyleSheet("background: #00a86b; color: white; font-weight: bold; border-radius: 4px;")
            self.auto_status_label.setText("自动交易: 运行中"); self.auto_status_label.setStyleSheet("color: #00d26a; font-weight: bold;")
            self.log("自动交易: 已启动"); threading.Thread(target=self._auto_trade_loop, daemon=True).start()
        else:
            self.btn_auto.setText("▶ 启动自动交易")
            self.btn_auto.setStyleSheet("background: #252540; color: #00d26a; border: 1px solid #00a86b; font-weight: bold; border-radius: 4px;")
            self.auto_status_label.setText("自动交易: 已停止"); self.auto_status_label.setStyleSheet("color: #7a7a9e;")
            self.log("自动交易: 已停止")

    def _connect_broker(self):
        """连接券商, 扫描品种 (同步, 点击按钮或启动时调用)"""
        self.log("─" * 40)
        self.log("🔍 正在连接券商...")
        self._sel_btn.setText("🔍 检测中...")
        try:
            bi = auto_setup_broker()
        except Exception as e:
            self.log(f"   ✗ 连接异常: {e}")
            bi = {"broker": "错误", "server": str(e)[:80], "symbols": ["XAUUSD"], "warnings": [f"异常: {e}"]}

        self.log(f"🏢 券商: {bi.get('broker','?')} | 服务器: {bi.get('server','?')}")
        syms = bi.get("symbols", [])
        self.log(f"📋 已匹配品种 ({len(syms)}个): {', '.join(syms) if syms else '无'}")
        for w in bi.get("warnings", []):
            self.log(f"   {w}")
        # 初始化所有品种 (symbol_select + 验证数据可读)
        if syms:
            _ensure_symbols_ready(SYMBOLS)
        # 更新品类菜单
        self._rebuild_category_selector()
        # 连接后检查 AutoTrading 状态
        at = check_autotrading()
        self._autotrading_ok = at.get("enabled", False)
        if self._autotrading_ok:
            self.log("✅ MT5 AlgoTrading 已开启")
        else:
            self.log("⚠  MT5 AutoTrading 未开启 — 点击MT5工具栏 ⚡AlgoTrading 按钮")
        self.log("✅ 券商连接完成")

        # 后台自动检查更新 (每24h一次)
        QTimer.singleShot(5000, self._auto_check_update)

    def _rebuild_category_selector(self):
        """重建品类选择器 (品种列表变更后调用)"""
        ALL_CATEGORIES = {
            "🥇 黄金":   ["XAUUSD"],
            "🪙 BTC":    ["BTCUSD"],
        }
        CATEGORIES = {}
        for cat, syms in ALL_CATEGORIES.items():
            available = [s for s in syms if s in SYMBOLS]
            if available:
                CATEGORIES[cat] = available
        self._cat_map = CATEGORIES
        self.log(f"📋 品类菜单重建: {list(CATEGORIES.keys())}")
        # 更新选择按钮文字
        self._update_sel_btn()

    def _update_sel_btn(self):
        """更新选择按钮文字"""
        init_name = SYMBOL_NAMES.get(self.symbol, self.symbol)
        init_cat = ""
        for cat, syms in self._cat_map.items():
            if self.symbol in syms: init_cat = cat; break
        btn_text = f"{init_cat} > {init_name} {self.symbol} ▾" if init_cat else f"{init_name} {self.symbol} ▾"
        if hasattr(self, '_sel_btn'):
            self._sel_btn.setText(btn_text)

    def _hot_reload(self):
        """热重载: 加载参数+重载模块. 代码修改需重启自动交易生效"""
        import importlib, types
        was_auto = self.auto_enabled
        if was_auto:
            self.auto_enabled = False; time.sleep(0.5)  # 让旧循环退出

        self.params = load_params(self.symbol)
        self.log("配置已重新加载")

        for mod_name in ["btc_panel", "hmm_state"]:
            try:
                mod = sys.modules.get(mod_name)
                if mod:
                    importlib.reload(mod)
                    self.log(f"  {mod_name} 已热重载")
            except Exception as e:
                self.log(f"  {mod_name}: {e}")

        from btc_panel import SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS, DEFAULT_PARAMS
        # 更新模块全局引用 (热重载后btc_panel的SYMBOLS可能变了)
        import btc_panel_qt as _self_mod
        _self_mod.SYMBOLS = SYMBOLS
        _self_mod.SYMBOL_NAMES = SYMBOL_NAMES
        _self_mod.SYMBOL_PARAMS = SYMBOL_PARAMS
        for k, w in self.param_widgets.items():
            w.setText(str(self.params.get(k, DEFAULT_PARAMS.get(k, ""))))

        if was_auto:
            self.auto_enabled = True
            threading.Thread(target=self._auto_trade_loop, daemon=True).start()
            self.log("自动交易已用新代码重启")
        else:
            self.log("热重载完成, 新配置已生效. 代码修改请手动重启自动交易")

    def _delayed_init(self):
        try:
            from hmm_state import load_model; load_model()
        except: pass
        # 【关键修复】先连券商, 再启动数据循环
        # QTimer.singleShot 不阻塞, 但需要确保 broker 在数据抓取前就绪
        # 改为先同步连接, 再启动定时器
        self._connect_broker()
        self._start_update_timer()

    def _start_update_timer(self):
        self._update_timer = QTimer(); self._update_timer.timeout.connect(self._trigger_fetch)
        self._update_timer.start(60000); self._trigger_fetch()

    def _trigger_fetch(self):
        if self._fetch_busy: return
        self._fetch_busy = True
        threading.Thread(target=self._fetch_and_update, daemon=True).start()

    def _fetch_and_update(self):
        _t0 = time.time()
        _round = getattr(self, '_fetch_round', 0) + 1
        self._fetch_round = _round
        sym_name = SYMBOL_NAMES.get(self.symbol, self.symbol)
        self.signals.log_msg.emit(f"════════ 第{_round}轮刷新 [{sym_name}] ════════")

        # 连接健康状态
        _conn_fail_count = getattr(self, '_conn_fail_count', 0)

        try:
            # Step 1: MT5数据获取
            _t1 = time.time()
            self.signals.log_msg.emit(f"📡 [1/6] 连接MT5获取数据...")
            data, ml, resonance, filter_info = fetch_dashboard_data(self.symbol, self.params)
            _t_data = time.time() - _t1
            if data and data.get("price"):
                p = data.get("price", 0)
                self._conn_fail_count = 0
                self.mt5_status_led.setText("● 已连接"); self.mt5_status_led.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 8px; color: #00d26a; background: #0d1a15; border: 1px solid #1a5533;")
                self.signals.log_msg.emit(f"   ✓ 报价 ${p:,.2f} | K线获取完成 ({_t_data:.1f}s)")
            else:
                self._conn_fail_count = getattr(self, '_conn_fail_count', 0) + 1
                self.signals.log_msg.emit(f"   ✗ MT5数据获取失败 (连续{self._conn_fail_count}次)")
                # 连续失败≥3次 → 尝试重连
                if self._conn_fail_count >= 3:
                    self.signals.log_msg.emit(f"🔄 连续{self._conn_fail_count}次失败，强制重连MT5...")
                    self.mt5_status_led.setText("⟳ 重连中..."); self.mt5_status_led.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 8px; color: #e0a800; background: #1a1500; border: 1px solid #553300;")
                    if mt5_reconnect():
                        self.signals.log_msg.emit(f"   ✓ MT5重连成功")
                        self._conn_fail_count = 0
                    else:
                        self.signals.log_msg.emit(f"   ✗ MT5重连失败，等待下轮重试")
            if ml and ml.get("ready"):
                ml_dir_s = "多" if ml.get("signal")==1 else ("空" if ml.get("signal")==-1 else "无")
                self.signals.log_msg.emit(f"   ✓ ML引擎: 看{ml_dir_s} {ml.get('confidence',0):.0%} | 强信号={'是' if ml.get('strong') else '否'}")
            if resonance:
                buys = sum(1 for r in resonance if r.get("signal")==1)
                sells = sum(1 for r in resonance if r.get("signal")==-1)
                self.signals.log_msg.emit(f"   ✓ 多周期共振: {buys}多/{sells}空 (共{len(resonance)}周期)")

            # Step 2: HMM状态
            if self.symbol in self._hmm_symbols:
                _t2 = time.time()
                self.signals.log_msg.emit(f"🧠 [2/6] HMM市场状态识别...")
                try:
                    from hmm_state import predict_current_state
                    real_sym = _real_symbol(self.symbol)
                    self._hmm_state = predict_current_state(real_sym)
                except Exception as e:
                    self._hmm_state = {"state":-1,"label":f"错误:{e}","confidence":0}
                    self.signals.log_msg.emit(f"   ✗ HMM异常: {e}")
                else:
                    hmm = self._hmm_state
                    if hmm.get("state",-1) >= 0:
                        self.signals.log_msg.emit(f"   ✓ {hmm['label']} (置信度{hmm['confidence']:.0%}, 预计持续{hmm.get('expected_duration',0)}根H4)")
                        key = f"{hmm.get('state')}_{hmm.get('label')}"
                        if key != self._last_hmm_log:
                            self._last_hmm_log = key
                _t_hmm = time.time() - _t2
            else:
                self.signals.log_msg.emit(f"🧠 [2/6] HMM: {sym_name}未配置, 跳过")

            # Step 3: 发送到UI
            self.signals.log_msg.emit(f"🖥️ [3/6] 更新界面...")
            self.signals.update_ui.emit(data, ml, resonance, filter_info or {})

            _t_total = time.time() - _t0
            self.signals.log_msg.emit(f"──────── 刷新完成 (耗时{_t_total:.1f}s) ────────")
        except Exception as e:
            self.signals.log_msg.emit(f"❌ 刷新异常: {e}")
            import traceback; self.signals.log_msg.emit(f"   {traceback.format_exc().splitlines()[-1]}")
        finally:
            self._fetch_busy = False

    def _update_ui(self, data, ml, resonance, filter_info):
        self._cached_filter_info = filter_info
        try:
            # 🔍 验证信号卡组件是否正常（调试用）
            if getattr(self, '_sig_check_done', False) is False:
                self._sig_check_done = True
                sig_parts = [
                    ('main_signal_icon', '◆'), ('sig_label', '等待数据...'),
                    ('hmm_label', 'HMM: '), ('sig_bar', None), ('sig_text', ''),
                    ('main_signal_reason', '')
                ]
                for name, default in sig_parts:
                    widget = getattr(self, name, None)
                    if widget is None:
                        self.signals.log_msg.emit(f"⚠️ 信号卡组件缺失: {name}")
                    elif not widget.isVisible():
                        self.signals.log_msg.emit(f"⚠️ 信号卡组件不可见: {name} → 强制显示")
                        widget.setVisible(True)
                    else:
                        txt = widget.text() if hasattr(widget, 'text') else '(widget)'
                        self.signals.log_msg.emit(f"✅ 信号卡组件OK: {name} = '{txt}'")

            self._cached_data = data; self._cached_ml = ml
            if resonance and len(resonance) > 0:
                self._cached_resonance = resonance; self._resonance_fail_count = 0
            else:
                self._resonance_fail_count += 1
                if self._resonance_fail_count > 3: self._cached_resonance = None

            # ── 价格 ──
            p = data.get("price", 0)
            if p:
                self.price_big.setText(f"$ {p:,.2f}")
                self.price_sub.setText(f"Bid: ${p:,.2f}  Ask: ${data.get('ask',0):,.2f}")
                self.mt5_status_led.setText("● 已连接"); self.mt5_status_led.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 8px; color: #00d26a; background: #0d1a15; border: 1px solid #1a5533;")
            else:
                self.mt5_status_led.setText("✗ 断连"); self.mt5_status_led.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 8px; color: #ff4444; background: #1a0d0d; border: 1px solid #552222;")

            # ── 持仓 ──
            pos = data.get("position")
            if pos:
                self._has_position = True; self._position_side = pos["side"]
                pnl = pos["profit"]; pc = GREEN if pnl >= 0 else RED
                self.pos_side.setText("📈 多" if pos["side"]=="多" else "📉 空")
                self.pos_side.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {pc};")
                self.pos_detail.setText(f"入场: ${pos['entry']:,.0f}  |  手数: {pos['volume']}  |  {'+' if pnl>=0 else ''}${pnl:.2f}")
                self.pos_detail.setStyleSheet(f"color: {pc}; font-size: 18px;")
            else:
                self._has_position = False; self._position_side = None
                self.pos_side.setText("空仓"); self.pos_side.setStyleSheet("font-size: 22px; font-weight: bold; color: #7a7a9e;")
                self.pos_detail.setText("无当前持仓"); self.pos_detail.setStyleSheet("color: #7a7a9e; font-size: 13px;")

            self.bal_label.setText(f"余额: ${data.get('balance',0):,.2f}")
            self.equity_label.setText(f"净值: ${data.get('equity',0):,.2f}")
            broker = data.get("broker",""); login = data.get("login","")
            if broker: self.broker_label.setText(f"券商: {broker}")
            if login: self.login_label.setText(f"账号: {login}")

            if data.get("balance"): self.signals.update_risk.emit(get_daily_pnl())

            # ── 综合信号计算（唯一信号源）──
            signal = get_trade_signal(self.symbol, self.params)
            dir_val = signal.get("direction", 0)
            strength = signal.get("strength", "弱")
            reason = signal.get("reason", "")
            conf = signal.get("confidence", 0)
            components = signal.get("components", {})
            weighted = signal.get("weighted", {"BUY": 0, "SELL": 0})
            ml_dir = signal.get("ml_dir", 0)
            ml_conf = signal.get("ml_confidence", 0)
            conflict = signal.get("conflict", False)
            
            # 各层日志
            for key, label in [("base","基频面(权重2.5)"), ("harmonic","谐波段(权重2.0)"), ("pulse","脉冲层(权重1.0)"), ("hmm","HMM(权重1.5)")]:
                sv = components.get(key, 0)
                sdir = "做多" if sv==1 else ("做空" if sv==-1 else "中性")
                self.signals.log_msg.emit(f"   • {label}: {sdir}")
            w_buy = weighted.get("BUY", 0); w_sell = weighted.get("SELL", 0)
            w_label = "做多" if w_buy > w_sell else ("做空" if w_sell > w_buy else "中性")
            self.signals.log_msg.emit(f"   → 加权结果: {w_label} (多{w_buy:.1f} vs 空{w_sell:.1f})")
            
            # ── 主信号: 用户只看这一个 ──
            # 设计原则: 只有当信号强到可交易时才给方向; 其余一律告诉用户"不动"
            if conflict and strength == "弱":
                # 两套系统打架 + 方向弱 → 坚决观望
                icon = "⚠"; text = "信号分歧"; action_text = "不建议开仓 · 等待方向统一"
                icon_color = "#e0a800"; text_color = "#e0a800"
                bar_val = 0; bar_clr = "#e0a800"
            elif dir_val == 0:
                # 无方向
                icon = "⏸"; text = "观望"; action_text = "信号未明确"
                icon_color = GRAY; text_color = GRAY
                bar_val = 0; bar_clr = GRAY
            elif strength == "强烈":
                # ★ 强烈信号 → 建议开仓
                icon = "◆"; text = "做多" if dir_val==1 else "做空"
                action_text = "★ 建议开仓" if dir_val==1 else "★ 建议开仓"
                icon_color = GREEN if dir_val==1 else RED
                text_color = GREEN if dir_val==1 else RED
                bar_val = int(conf*100); bar_clr = GREEN if dir_val==1 else RED
            elif strength == "中等":
                # 中等信号 → 可以参考
                icon = "◇"; text = "做多" if dir_val==1 else "做空"
                action_text = "可参考开仓" if dir_val==1 else "可参考开仓"
                icon_color = "#44cc44" if dir_val==1 else "#cc4444"
                text_color = "#44cc44" if dir_val==1 else "#cc4444"
                bar_val = int(conf*100); bar_clr = "#44cc44" if dir_val==1 else "#cc4444"
            else:
                # 弱信号 → 不建议
                icon = "─"; text = "信号弱"
                action_text = "不建议开仓 · 信号不足"
                icon_color = GRAY; text_color = GRAY
                bar_val = int(conf*100); bar_clr = GRAY

            # 置信度百分比单独显示
            if conf > 0 and strength in ("强烈","中等"):
                full_text = f"{icon} {text} {conf:.0%}"
            elif conf > 0:
                full_text = f"{icon} {text}"
            else:
                full_text = f"{icon} {text}"

            self.main_signal_icon.setText(icon)
            self.main_signal_icon.setStyleSheet(f"color: {icon_color}; font-size: 32px; font-weight: bold;")
            self.sig_label.setText(full_text)
            self.sig_label.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {text_color};")
            self.main_signal_reason.setText(action_text)
            if "建议开仓" in action_text:
                self.main_signal_reason.setStyleSheet(f"color: {text_color}; font-size: 14px; font-weight: bold; padding: 2px 8px; border-radius: 6px; background: {text_color}15;")
            else:
                self.main_signal_reason.setStyleSheet(f"color: {text_color}; font-size: 12px; padding: 2px 8px;")

            # ── 多空比例条: 可视化力量对比 ──
            try:
                buy_pct = w_buy / (w_buy + w_sell) * 100 if (w_buy + w_sell) > 0 else 50
                sell_pct = 100 - buy_pct
                # 更新百分比标签
                self.buy_label.setText(f"做多 {buy_pct:.0f}%")
                self.sell_label.setText(f"做空 {sell_pct:.0f}%")
                # 动态调整比例条 stretch factor (比例变 → 条自动伸缩)
                bar_layout = self.bar_container.layout()
                stretch_total = max(1, int(buy_pct + sell_pct))
                buy_stretch = max(1, int(buy_pct))
                sell_stretch = max(1, int(sell_pct))
                # 移除旧stretch, 设置新的
                bar_layout.setStretch(0, buy_stretch)
                bar_layout.setStretch(1, sell_stretch)
            except Exception as _pe:
                self.signals.log_msg.emit(f"   ⚠ 比例条异常: {_pe}")
                self.buy_label.setText(f"做多 {w_buy:.1f}")
                self.sell_label.setText(f"做空 {w_sell:.1f}")

            # 信号条
            bar_text = f"{'看多' if dir_val==1 else ('看空' if dir_val==-1 else '观望')} {bar_val}%" if dir_val else ""
            self.sig_bar.set_value(bar_val if dir_val==1 else -bar_val, bar_clr, bar_text)
            
            # ── 各层投票 + ML引擎 + 加权 ──
            ml_status = ""
            if ml_dir == 1: ml_status = f"ML引擎 ▲看多 {ml_conf:.0%}"
            elif ml_dir == -1: ml_status = f"ML引擎 ▼看空 {ml_conf:.0%}"
            else: ml_status = "ML引擎 ─ 未就绪"
            w_info = f"加权 多{w_buy:.1f} vs 空{w_sell:.1f}"
            
            parts = []
            for layer_key, label in [("base","基频面"),("harmonic","谐波段"),("pulse","脉冲层"),("hmm","HMM")]:
                sv = components.get(layer_key, 0)
                sym = "▲" if sv==1 else ("▼" if sv==-1 else "─")
                parts.append(f"{sym}{label}")
            
            conflict_warn = "⚠ 信号分歧 | " if conflict else ""
            self.sig_text.setText(f"{conflict_warn}{ml_status}  |  {w_info}  |  {' '.join(parts)}")
            self.main_signal_reason.setText(reason)
            
            self.signals.log_msg.emit(f"   ✓ 主信号: [{icon}] {text}")

            # ── HMM标签 ──
            hmm = self._hmm_state
            if hmm and hmm["state"] >= 0:
                hl = hmm["label"]; hc = hmm["confidence"]
                cols = {"📈 强势趋势":"#00cc80","📉 高波回撤":"#e07080","📊 窄幅整理":"#e0a800"}
                c = cols.get(hl,"#7a7a9e")
                durable = 1/(1-hmm["self_prob"]) if hmm.get("self_prob",0)<1 else 99
                self.hmm_label.setText(f"HMM: {hl}")
                self.hmm_label.setStyleSheet(f"color: {c}; font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #2a2a44;")
                self.hmm_conf.setText(f"置信度 {hc:.0%} | 预计持续 {durable:.0f}根H4")
            else:
                # 显示具体原因而非仅 "-"
                reason = hmm.get("label", "等待数据") if hmm else "等待数据"
                self.hmm_label.setText(f"HMM: {reason}")
                self.hmm_label.setStyleSheet("color: #7a7a9e; font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #3a3a55;")
                self.hmm_conf.setText("")

            # ── 按钮状态 ──
            if self._has_position:
                self.btn_close.setProperty("active",True); self.btn_close.setText("📊 平仓 (CLOSE)")
                self.btn_buy.setProperty("active",True); self.btn_buy.setText("📈 做多 (BUY)")
                self.btn_sell.setProperty("active",True); self.btn_sell.setText("📉 做空 (SELL)")
                self.btn_reverse.setProperty("active",True)
                self.btn_reverse.setText(f"⚡ 反手{'空' if self._position_side=='多' else '多'}")
            else:
                self.btn_close.setProperty("active",False); self.btn_close.setText("📊 平仓 (CLOSE)")
                self.btn_reverse.setProperty("active",False); self.btn_reverse.setText("🔄 一键反转")
                self.btn_buy.setProperty("active",True); self.btn_buy.setText("📈 做多 (BUY)")
                self.btn_sell.setProperty("active",True); self.btn_sell.setText("📉 做空 (SELL)")
            for btn in [self.btn_buy,self.btn_sell,self.btn_close,self.btn_reverse]:
                btn.style().unpolish(btn); btn.style().polish(btn)

            # ── 详情区 [5/6] ──
            self.signals.log_msg.emit(f"📋 [5/6] 更新详情区...")
            try:
                rd2 = []
                if ml.get("ready"):
                    ms = ml["signal"]; mc = ml["confidence"]*100
                    rd2.append(("核心引擎","▲做多" if ms==1 else "▼做空",f"{mc:.0f}%",mc,GREEN if ms==1 else RED))
                name_map = {"1h":"脉冲层","4h":"谐波段","1d":"基频面"}
                rd_lookup = {r.get("name",""): r for r in (resonance or []) if r.get("name") in name_map}
                self.signals.log_msg.emit(f"   resonance 可用: {len(resonance or [])}条, 匹配: {len(rd_lookup)}个")
                for r_name, label in [("1h","脉冲层"),("4h","谐波段"),("1d","基频面")]:
                    r = rd_lookup.get(r_name)
                    if r:
                        sig = r.get("signal", 0)
                        rsi = r.get("rsi", 50)
                        dt = "▲做多" if sig==1 else ("▼做空" if sig==-1 else "─ 中性")
                        bc = GREEN if sig==1 else (RED if sig==-1 else GRAY)
                        bp = max(0, min(100, abs(rsi - 50) / 30 * 100))
                        rd2.append((label, dt, f"RSI{rsi:.0f}", bp, bc))
                    else:
                        rd2.append((label, "─", "", 0, GRAY))
                self.signals.log_msg.emit(f"   rd2 条目数: {len(rd2)}")
                for label, dt, pct_t, bp, bc in rd2:
                    if label in self.detail_rows:
                        ds,dp,bar = self.detail_rows[label]
                        ds.setText(dt); cl2 = GREEN if '多' in dt else (RED if '空' in dt else '#e0e0e0')
                        ds.setStyleSheet(f"color: {cl2}; font-weight: bold; font-size: 12px;")
                        dp.setText(pct_t); bar.set_value(bp,bc)
                    else:
                        self.signals.log_msg.emit(f"   ⚠ detail_rows 缺少: {label}")
            except Exception as _de:
                self.signals.log_msg.emit(f"   ⚠ 详情区异常: {_de}")

            # ── [6/6] 完成 ──
            bal = data.get('balance', 0)
            eq = data.get('equity', 0)
            pos_str = f"持仓:{self._position_side}({'+' if (pos and pos['profit']>=0) else ''}${pos['profit']:.0f})" if pos else "空仓"
            self.signals.log_msg.emit(f"💰 [6/6] 账户: 余额${bal:,.0f} 净值${eq:,.0f} | {pos_str}")

        except Exception as e:
            import traceback
            self.signals.log_msg.emit(f"❌ UI更新异常: {e}")
            self.signals.log_msg.emit(f"   {traceback.format_exc().splitlines()[-1]}")

    def _update_risk_status(self, daily):
        pnl = daily.get("pnl",0); bal = daily.get("balance",0)
        start = daily.get("start_balance",bal) or 1
        dd_pct = (start-bal)/start*100
        self.sb_risk.setText(f"日: {'+' if pnl>=0 else ''}${pnl:.0f}  回撤: {dd_pct:.1f}%")

    def _apply_params(self):
        for k, w in self.param_widgets.items():
            try: self.params[k] = float(w.text())
            except: pass
        save_params(self.params, symbol=self.symbol); self.log("参数已保存")

    def _reset_params(self):
        global DEFAULT_PARAMS
        self.params = dict(DEFAULT_PARAMS)
        # 合入当前品种专属默认值 (如 lot_min, sl_min 等)
        sp = SYMBOL_PARAMS.get(self.symbol, {})
        for k, v in sp.items(): self.params[k] = v
        for k, w in self.param_widgets.items():
            w.setText(str(self.params.get(k,DEFAULT_PARAMS.get(k,""))))
        self.log("参数已重置")

    def _about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(self, "About", f"BTC Panel v{CURRENT_VERSION}\nXAUUSD + BTCUSD Quantitative Trading")

    def _poll_update(self):
        """主线程轮询: 检测到 _pending_update 时弹出更新窗口"""
        if self._pending_update:
            info = self._pending_update
            self._pending_update = None
            self._prompt_update(info)

    def _check_update(self):
        """手动检查更新"""
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        self.log("🔄 正在检查更新...")
        self.signals.update_async = check_update_remote
        threading.Thread(target=self._do_check_update, daemon=True).start()

    def _do_check_update(self):
        info = check_update_remote()
        if info.get("error") and "getaddrinfo" not in info["error"]:
            self.signals.log_msg.emit(f"   ⚠ 更新检查失败: {info['error']}")
            return
        if info["has_update"]:
            ver = info["remote_version"]
            size_mb = info.get("size", 0) / 1024 / 1024
            self.signals.log_msg.emit(f"   🆕 发现新版本 v{ver}! ({size_mb:.1f}MB)")
            self._update_info = info
            # 保存到成员变量，主线程定时器轮询触发弹窗（信号跨线程可能丢失）
            self._pending_update = info
        else:
            self.signals.log_msg.emit(f"   ✓ 已是最新版本 v{CURRENT_VERSION}")

    def _prompt_update(self, info: dict):
        """弹出更新提示窗口"""
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        ver = info["remote_version"]
        notes = info.get("notes", "")
        url = info["download_url"]
        size_mb = info.get("size", 0) / 1024 / 1024

        box = QMessageBox(self)
        box.setWindowTitle("发现新版本")
        box.setText(f"BTC Panel v{ver} 可用\n\n{notes}\n\n下载大小: {size_mb:.1f} MB")
        box.setIcon(QMessageBox.Information)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("下载更新")
        box.button(QMessageBox.No).setText("稍后提醒")
        box.setStyleSheet("QMessageBox { background: #1a1a2e; color: #e0e0e0; }")

        if box.exec() == QMessageBox.Yes:
            self._download_and_install(url, ver)

    def _download_and_install(self, url: str, new_ver: str):
        """下载更新并安装 (进度通过信号更新, 避免线程崩溃)"""
        from PySide6.QtWidgets import QProgressDialog, QMessageBox
        prog = QProgressDialog(f"正在下载 v{new_ver}...", "取消", 0, 100, self)
        prog.setWindowTitle("更新 BTC Panel")
        prog.setMinimumDuration(0)
        prog.setStyleSheet("QProgressDialog { background: #1a1a2e; color: #e0e0e0; }")
        prog.show()

        dl_done = {"path": "", "error": ""}

        def on_progress(pct, downloaded, total):
            self.signals.dl_progress.emit(pct, downloaded, total)

        def update_progress(pct, downloaded, total):
            mb = downloaded / 1024 / 1024
            total_mb = total / 1024 / 1024 if total > 0 else 0
            if total_mb > 0:
                prog.setLabelText(f"正在下载 v{new_ver}... {mb:.1f} / {total_mb:.1f} MB")
            else:
                prog.setLabelText(f"正在下载 v{new_ver}... {mb:.1f} MB")
            prog.setValue(pct)

        def on_done():
            prog.close()
            if dl_done["path"]:
                self.log(f"✅ 更新下载完成")
                time.sleep(0.5)
                apply_update(dl_done["path"])
            else:
                self.log(f"❌ 更新下载失败: {dl_done.get('error', '')}")
                QMessageBox.warning(self, "下载失败", "无法下载更新文件, 请稍后重试或手动下载。")

        self.signals.dl_progress.connect(update_progress)

        def do_dl():
            path = download_update(url, version=new_ver, progress_callback=on_progress)
            dl_done["path"] = path or ""
            if not path:
                dl_done["error"] = "下载失败"
            self.signals.dl_done_signal.emit()

        self.signals.dl_done_signal = Signal()
        self.signals.dl_done_signal.connect(on_done)
        threading.Thread(target=do_dl, daemon=True).start()

    def _auto_check_update(self):
        """启动后自动检查更新(静默, 每24h一次)"""
        import pickle
        last_check_file = "last_update_check.dat"
        now = time.time()
        try:
            if os.path.exists(last_check_file):
                with open(last_check_file, "rb") as f:
                    last = pickle.load(f)
                if now - last < 86400:  # 24小时
                    return
        except: pass
        try:
            with open(last_check_file, "wb") as f:
                pickle.dump(now, f)
        except: pass
        # 后台静默检查
        def _check():
            info = check_update_remote()
            if info["has_update"]:
                self.signals.log_msg.emit(f"🆕 [更新] 发现新版本 v{info['remote_version']}!")
                self._update_info = info
                # 清除24h缓存, 确保下次检查会再次弹窗
                try: os.remove(last_check_file)
                except: pass
                # 保存到成员变量，主线程定时器轮询触发弹窗
                self._pending_update = info
            else:
                self.signals.log_msg.emit(f"   ✓ 已是最新版本 v{CURRENT_VERSION}")
        threading.Thread(target=_check, daemon=True).start()

    def _init_tooltips(self):
        """所有名词的悬停解释(纯文本, 删除本行调用即可全部移除)"""
        self.price_big.setToolTip("实时报价, Bid+Ask/2\nBid(卖出价)=你做多平仓/做空开仓价\nAsk(买入价)=你做多开仓/做空平仓价\n点差=Ask-Bid, 越小成本越低")
        self.price_sub.setToolTip("Bid: 你卖出得到的价格 | Ask: 你买入要付的价格")
        self.pos_side.setToolTip("持仓方向\n多=买涨(Long), 按Ask买入->按Bid卖出\n空=买跌(Short), 按Bid卖出->按Ask买入")
        self.pos_detail.setToolTip("入场价=开仓成交价 | 手数=持仓量 | 盈亏=浮动盈亏")
        self.broker_label.setToolTip("券商名称, 从MT5终端读取")
        self.login_label.setToolTip("MT5账号, 当前登录的交易账户")
        self.bal_label.setToolTip("余额(Balance)=已平仓交易的资金, 不含浮动盈亏")
        self.equity_label.setToolTip("净值(Equity)=余额+浮动盈亏, 即实际可用资金\n净值<余额说明当前持仓在亏钱")
        self.sig_label.setToolTip("综合信号 · 加权投票唯一方向\n◆ 做多/做空 强烈: ★建议开仓\n◇ 做多/做空 中等: 可参考开仓\n─ 信号弱: 不建议开仓\n⚠ 信号分歧: 加权与引擎方向相悖, 不建议开仓")
        self.sig_bar.setToolTip("信号强度条\n中线=方向分界, 绿右=做多强度, 红左=做空强度")
        self.sig_text.setToolTip("共振 X多/Y空: X个框架看多,Y个看空\n引擎方向: 核心ML预测方向和置信度")
        self.hmm_label.setToolTip("HMM隐马尔可夫模型, 识别市场状态\n强势趋势=低波动+持续上涨, 只做多不做空\n高波回撤=高波动+价格回落, 只做空不做多\n窄幅整理=低波动+横盘, 多空都正常\n置信度=模型确定度, 预计持续=统计期望非锁定")
        self.hmm_conf.setToolTip("置信度=模型确定度 | 预计持续=统计期望")
        self.btn_buy.setToolTip("做多(BUY): 按Ask买入, 等涨价后按Bid卖出\n开仓不碰现有持仓, 支持多仓位平行持有")
        self.btn_sell.setToolTip("做空(SELL): 按Bid卖出, 等跌价后按Ask买入\n开仓不碰现有持仓, 支持多仓位平行持有")
        self.btn_close.setToolTip("平仓(CLOSE): 平掉当前所有持仓\n有持仓时金色可用, 无持仓时灰色")
        self.btn_reverse.setToolTip("一键反转: 先平掉持仓再反向开新仓\n注意: 中间有几秒空窗期")
        self.btn_auto.setToolTip("自动交易开关\n启动后自动: 监控共振信号+HMM确认+风控检查->开仓, 开启移动止损和盈利保护\n前提: MT5需开启Algo Trading开关")
        self.auto_status_label.setToolTip("当前自动交易状态\n运行中=实时监控+自动开仓 | 已停止=只显示数据不执行交易")
        self.mt5_status_led.setToolTip("MT5连接状态\n已连接=MT5终端正常运行\n等待连接=MT5未启动或连接断开")
        self.sb_risk.setToolTip("日盈亏: 当日累计盈利/亏损\n回撤: 从当日最高净值下跌的百分比\n日亏或回撤超限将自动停止交易")
        self.log_area.setToolTip("交易日志, 记录所有开平仓/止损止盈/风控/异常")
        self.param_toggle.setToolTip("展开/收起策略参数面板")
        self._sel_btn.setToolTip("点击展开品类菜单选择交易品种")
        for cat, syms in self._cat_map.items():
            for sym in syms:
                pass  # tooltips via menu items

    def _auto_trade_loop(self):
        """自动交易主循环 (不手动管理MT5连接, 由btc_panel内部管理)"""
        _last_trade_time = datetime(2000,1,1)
        _peak_profit = 0.0
        _last_trail_mod = 0
        _last_trail_price = 0.0
        _loop_count = 0
        _consecutive_strong = 0      # 连续强信号计数 (同方向)
        _last_signal_dir = 0          # 上次强信号方向
        _reentry_until = None         # 止盈平仓后禁止重入到此时间
        self.log("🤖 ═══════════════════════════════════════════")
        self.log("🤖  自动交易引擎已启动")
        self.log(f"🤖  品种: {SYMBOL_NAMES.get(self.symbol, self.symbol)} ({self.symbol})")
        self.log(f"🤖  策略: 加权信号 + HMM过滤 + 风控 + 移动止损")
        self.log(f"🤖  开仓条件: 强信号连续2次确认 + 置信度≥75% + HMM通过 + 风控通过")
        # 检查AutoTrading状态
        at = check_autotrading()
        self._autotrading_ok = at.get("enabled", False)
        if self._autotrading_ok:
            self.log("🤖  ✅ MT5 AlgoTrading 已开启 — 可正常下单")
        else:
            self.log("🤖  ⚠  MT5 AlgoTrading 未开启 — 无法下单！点击MT5工具栏 ⚡ 按钮")
        self.log("🤖 ═══════════════════════════════════════════")
        while self.auto_enabled:
            _loop_count += 1
            try:
                now = datetime.now()
                self.params = load_params(self.symbol)
                thresh = int(self.params.get("resonance_threshold",2))
                cooldown = int(self.params.get("cooldown_minutes",5))
                profit_lock_trigger = float(self.params.get("profit_lock_trigger",15))
                profit_lock_pullback = float(self.params.get("profit_lock_pullback",30))

                # ── 风控：日亏检查 ──
                daily = get_daily_pnl()
                max_daily = float(self.params.get("max_daily_loss",100))
                if daily.get("pnl",0) <= -abs(max_daily):
                    self.log(f"🛑 风控: 日亏${abs(daily['pnl']):.0f}≥${max_daily}, 引擎暂停5分钟")
                    time.sleep(300); continue

                # ── 获取报价 (带自动重连) ──
                tick, info = get_mt5_tick(self.symbol)
                if not tick or not info:
                    _fails = getattr(self, '_trade_fail_count', 0) + 1
                    self._trade_fail_count = _fails
                    self.log(f"⚠️  报价获取失败 (连续{_fails}次)")
                    if _fails >= 3:
                        self.log(f"🔄 报价连续{_fails}次失败，尝试重连MT5...")
                        if mt5_reconnect():
                            self.log(f"   ✓ MT5重连成功")
                            self._trade_fail_count = 0
                            time.sleep(2); continue
                        else:
                            self.log(f"   ✗ MT5重连失败，30秒后重试")
                    time.sleep(10); continue

                # ── AutoTrading 检测 (每30轮检查一次) ──
                if _loop_count % 30 == 1:
                    at = check_autotrading()
                    self._autotrading_ok = at.get("enabled", False)
                    if not self._autotrading_ok:
                        self.log("⚠  MT5 AutoTrading 未开启 — 无法下单 — 点击MT5工具栏 ⚡按钮")
                self._trade_fail_count = 0

                # ── 市场状态检查 ──
                if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
                    self.log("⏸  市场已收盘 (周末/假期), 跳过交易")
                    time.sleep(60); continue

                price = tick.bid

                # 移动止损距离: 优先用品种STRATEGY_CFG百分比, 否则用通用点数
                _, strategy_cfg, _ = _load_symbol_params(self.symbol)
                trail_pct = float(strategy_cfg.get("trail_dist_pct", 0) or 0)
                if trail_pct > 0 and info.point:
                    trail_dist_points = int(trail_pct / 100 * price / info.point)
                else:
                    trail_dist_points = int(float(self.params.get("trail_dist", 300)))

                positions = get_mt5_positions(self.symbol)
                has_position = positions and len(positions) > 0

                # ── 有持仓：管理止盈止损 ──
                if has_position:
                    p = positions[0]
                    current_sl = p.sl or 0
                    try:
                        pnl = float(p.profit or 0)
                    except (TypeError, ValueError):
                        pnl = 0.0
                    side = "BUY" if p.type == 0 else "SELL"
                    side_cn = "多" if p.type == 0 else "空"

                    if _loop_count % 5 == 0:  # 每5轮输出一次持仓状态
                        self.log(f"📊 持仓监控: {side_cn} ${pnl:+.2f} | SL={current_sl:.1f} | 距止损={abs(price-current_sl):.1f}")

                    # ── 盈利回撤保护 ──
                    if pnl > _peak_profit:
                        if _loop_count % 3 == 0:
                            self.log(f"📈 盈利创新高: ${_peak_profit:.2f} → ${pnl:.2f}")
                        _peak_profit = pnl

                    if _peak_profit > 0:
                        pullback_pct = (_peak_profit - pnl) / _peak_profit * 100 if _peak_profit > 0 else 0
                        # 每次持仓轮都输出追高状态（便于排查）
                        if _loop_count % 2 == 0:
                            trigger_tag = "🔒激活" if _peak_profit > profit_lock_trigger else "⏳等待"
                            self.log(f"📉 回撤监控: 峰值${_peak_profit:.2f} | 当前${pnl:+.2f} | 回撤{pullback_pct:.1f}% | {trigger_tag}(触发>{profit_lock_trigger})")
                        
                        # 只在仍盈利时触发回撤平仓，亏损状态继续持有等待反转
                        if pnl > 0 and _peak_profit > profit_lock_trigger and pullback_pct >= profit_lock_pullback:
                            self.log(f"🔒 止盈触发! 峰值${_peak_profit:.1f} 回撤{pullback_pct:.0f}%≥{profit_lock_pullback}% → 自动平仓")
                            result = execute_trade("CLOSE", self.symbol, self.params)
                            self.log(f"{'✅' if result.get('ok') else '❌'} 平仓结果: {result.get('msg','')}")
                            _last_trade_time = now
                            _peak_profit = 0.0
                            _consecutive_strong = 0
                            _last_signal_dir = 0
                            # 止盈平仓后: 3倍冷却 + 2次信号确认, 防止立刻接飞刀
                            _reentry_until = now + timedelta(minutes=cooldown * 3)
                            self.log(f"⏸  止盈后保护: 禁止重入直到 {_reentry_until.strftime('%H:%M')} (冷却{cooldown*3}分钟+信号稳定确认)")

                    # 移动止损 (每60秒检查一次, 需盈利超过追$阈值)
                    now_ts = time.time()
                    trail_profit_threshold = float(self.params.get("trail_profit", 5))
                    if now_ts - _last_trail_mod >= 60 and pnl >= trail_profit_threshold:
                        point = info.point
                        tr_dist_price = trail_dist_points * point
                        if side == "BUY":
                            new_sl = price - tr_dist_price
                            if new_sl > current_sl + 50*point and abs(new_sl - _last_trail_price) > 20*point:
                                new_sl = round(new_sl, digits)
                                _last_trail_price = new_sl
                                _last_trail_mod = now_ts
                                self.log(f"📈 移动止损: 多单 SL {current_sl:.1f} → {new_sl:.1f} (锁定利润, 追≥${trail_profit_threshold})")
                                threading.Thread(target=modify_sl, args=(p.ticket,new_sl), daemon=True).start()
                        else:
                            new_sl = price + tr_dist_price
                            if new_sl < current_sl - 50*point:
                                if abs(new_sl - _last_trail_price) > 20*point:
                                    new_sl = round(new_sl, digits)
                                    _last_trail_price = new_sl
                                    _last_trail_mod = now_ts
                                    self.log(f"📉 移动止损: 空单 SL {current_sl:.1f} → {new_sl:.1f} (锁定利润, 追≥${trail_profit_threshold})")
                                    threading.Thread(target=modify_sl, args=(p.ticket,new_sl), daemon=True).start()

                    time.sleep(60); continue

                # ── 无持仓：检查信号开仓 ──
                # 止盈后重入保护: 3倍冷却期内禁止开仓
                if _reentry_until and now < _reentry_until:
                    remaining = (_reentry_until - now).total_seconds()
                    if _loop_count % 5 == 0:
                        self.log(f"⏸  止盈保护中: 还需{remaining:.0f}秒后解禁")
                    time.sleep(60); continue

                if (now - _last_trade_time).total_seconds() < cooldown*60:
                    remaining = cooldown*60 - (now - _last_trade_time).total_seconds()
                    if _loop_count % 10 == 0:
                        self.log(f"⏳ 冷却中: 还需{remaining:.0f}秒后可开仓")
                    time.sleep(30); continue

                # 获取引擎信号
                ml_data = getattr(self, '_cached_ml', None)
                if not ml_data or not ml_data.get("ready"):
                    if _loop_count % 10 == 0:
                        self.log("⏳ 等待引擎数据就绪...")
                    time.sleep(30); continue

                # ── 开仓条件1: 置信度≥75% ──
                confidence = ml_data.get("confidence", 0)
                if confidence < 0.75:
                    _consecutive_strong = 0; _last_signal_dir = 0
                    if _loop_count % 10 == 0:
                        self.log(f"🔍 信号检查: 置信度{confidence:.0%}<75% → 观望")
                    time.sleep(60); continue

                # ── 开仓条件2: 强信号(基频面+谐波段同向) ──
                is_strong = ml_data.get("strong", False)
                direction = ml_data.get("signal", 0)
                group_sigs = ml_data.get("group_signals", {})

                if not is_strong:
                    _consecutive_strong = 0; _last_signal_dir = 0
                    if _loop_count % 10 == 0:
                        self.log(f"🔍 信号检查: 非强信号(多周期矛盾) → 跳过")
                    time.sleep(60); continue

                # ── 开仓条件3: 信号稳定性 (同方向连续≥2次确认) ──
                if direction == _last_signal_dir:
                    _consecutive_strong += 1
                else:
                    _consecutive_strong = 1
                    _last_signal_dir = direction

                dir_label = "看多" if direction == 1 else "看空"
                if _consecutive_strong < 2:
                    if _loop_count % 3 == 0:
                        self.log(f"🔍 信号确认: 强{dir_label} 第{_consecutive_strong}/2次 (需连续2次才执行)")
                    time.sleep(60); continue

                # ── 开仓执行 ──
                if direction == 1:   # 看多
                    self.log(f"🔔 信号触发: 强看多 {confidence:.0%} | 组信号: {group_sigs}")
                    passed, reason = check_risk_gates(self.symbol, "BUY", self.params)
                    if not passed:
                        self.log(f"🛑 风控拦截(多): {reason} → 取消开仓")
                        _consecutive_strong = 0; _last_signal_dir = 0
                        time.sleep(60); continue
                    hmm_s = -1
                    fi = getattr(self, '_cached_filter_info', {})
                    if fi:
                        hmm_s = fi.get("hmm_state", -1)
                    if hmm_s == 2:
                        self.log(f"🛑 HMM拦截(多): 高波回撤状态 → 取消开多")
                        _consecutive_strong = 0; _last_signal_dir = 0
                        time.sleep(60); continue
                    self.log(f"✅ 全部通过 → 执行开多 (置信度{confidence:.0%})")
                    result = execute_trade("BUY", self.symbol, self.params)
                    self.log(f"{'✅' if result.get('ok') else '❌'} 开多结果: {result.get('msg','')}")
                    if result.get("ok"):
                        _last_trade_time = now
                        _peak_profit = 0.0
                        _consecutive_strong = 0
                        _last_signal_dir = 0
                        _reentry_until = None

                elif direction == -1: # 看空
                    self.log(f"🔔 信号触发: 强看空 {confidence:.0%} | 组信号: {group_sigs}")
                    passed, reason = check_risk_gates(self.symbol, "SELL", self.params)
                    if not passed:
                        self.log(f"🛑 风控拦截(空): {reason} → 取消开仓")
                        _consecutive_strong = 0; _last_signal_dir = 0
                        time.sleep(60); continue
                    hmm_s = -1
                    fi = getattr(self, '_cached_filter_info', {})
                    if fi:
                        hmm_s = fi.get("hmm_state", -1)
                    if hmm_s == 0:
                        self.log(f"🛑 HMM拦截(空): 强势趋势状态 → 取消开空")
                        _consecutive_strong = 0; _last_signal_dir = 0
                        time.sleep(60); continue
                    self.log(f"✅ 全部通过 → 执行开空 (置信度{confidence:.0%})")
                    result = execute_trade("SELL", self.symbol, self.params)
                    self.log(f"{'✅' if result.get('ok') else '❌'} 开空结果: {result.get('msg','')}")
                    if result.get("ok"):
                        _last_trade_time = now
                        _peak_profit = 0.0
                        _consecutive_strong = 0
                        _last_signal_dir = 0
                        _reentry_until = None

                time.sleep(120)
            except Exception as loop_err:
                try:
                    self.log(f"❌ 引擎异常: {loop_err}")
                except: pass
                time.sleep(30)

# ═══════════════════════════════════════════
# 单实例锁 — 防止同时打开多个面板
# ═══════════════════════════════════════════
_SINGLE_INSTANCE_PORT = 29888
_instance_lock_socket = None

def _acquire_single_instance():
    """绑定本地端口作为实例锁。成功返回 socket（需保持引用），失败返回 None（已有实例运行）。"""
    global _instance_lock_socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 1)
        s.bind(('127.0.0.1', _SINGLE_INSTANCE_PORT))
        s.listen(1)
        s.setblocking(False)
        _instance_lock_socket = s
        return True
    except socket.error:
        return False

def _bring_existing_window_to_front():
    """尝试将已运行的 BTC Panel 窗口提到最前面"""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        # 枚举所有顶层窗口，找到标题包含 "BTC Panel" 的
        found = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    if "BTC Panel" in title:
                        found.append(hwnd)
            return True
        user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
        if found:
            hwnd = found[0]
            # SW_RESTORE = 9, then bring to front
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass  # 激活失败也不影响，至少锁住了

def main():
    # ═══════════════════════════════════════
    # 单实例检测 (必须在一切操作之前)
    # ═══════════════════════════════════════
    if not _acquire_single_instance():
        # 已有实例在运行 — 尝试激活已有窗口然后退出
        _bring_existing_window_to_front()
        # 弹一个简单的消息框 (需要 QApplication)
        app = QApplication(sys.argv)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, "BTC Panel", "程序已在运行中，请检查任务栏或系统托盘。")
        sys.exit(0)

    # ═══════════════════════════════════════
    # 授权验证 (在任何窗口显示之前)
    # ═══════════════════════════════════════
    lic = check_license()
    if not lic["valid"]:
        hwid = lic.get("hwid", get_hwid())
        key = show_license_dialog(hwid, trial_left=0, expired=lic.get("expired", False))
        if not key:
            sys.exit(0)  # 用户点了退出
        # 重新检查
        lic = check_license()
        if not lic["valid"]:
            # 弹一次消息后退出
            app = QApplication(sys.argv)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "授权失败", "序列号无效，程序将退出。")
            sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    QToolTip.setFont(QFont("Microsoft YaHei", 9))
    p = app.palette()
    p.setColor(QPalette.ToolTipBase, QColor("#1a1a2e"))
    p.setColor(QPalette.ToolTipText, QColor("#b0b0c0"))
    app.setPalette(p)
    window = MainWindow()
    window._license_info = lic  # 保存授权信息
    window._update_license_label(lic)  # 状态栏显示授权状态
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
