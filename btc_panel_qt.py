#!/usr/bin/env python3
"""
BTC AI 交易面板 v3 - PySide6 专业桌面版
多品类支持: 贵金属/指数/外汇/商品
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

from btc_panel import (
    execute_trade, fetch_all_mt5_data, check_risk_gates, get_daily_pnl,
    _mt5_lock, MT5_PATH, DEFAULT_PARAMS, load_params, save_params,
    SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS,
    is_trade_time_allowed,
)
import MetaTrader5 as mt5

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
QStatusBar { background: #15152a; color: #7a7a9e; border-top: 1px solid #222244; font-size: 12px; }
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
        self.setWindowTitle("BTC AI 交易面板 v3 - #60107268")
        self.setMinimumSize(800, 950); self.resize(850, 980)
        self.setStyleSheet(DARK_QSS)
        self.symbol = "XAUUSD"
        self.params = load_params()
        self.auto_enabled = False
        self._has_position = False; self._position_side = None
        self._fetch_busy = False; self._binance_ok = False
        self._cached_data = {}; self._cached_ml = {}; self._cached_resonance = []
        self._resonance_fail_count = 0
        self._hmm_state = {"state": -1, "label": "加载中...", "confidence": 0}
        self._last_hmm_log = ""
        self._hmm_symbols = {"XAUUSD","XAGUSD","US30","NAS100","SPX500","HK50","USOIL","UKOIL","BTCUSD"}
        self.signals = UISignals()
        self.signals.log_msg.connect(self._on_log)
        self.signals.update_ui.connect(self._update_ui)
        self.signals.update_risk.connect(self._update_risk_status)
        self._setup_menubar()
        self._setup_ui()
        self._setup_statusbar()
        self._init_tooltips()  # 所有名词解释
        self._delayed_init()

    def _setup_menubar(self):
        mb = self.menuBar()
        f=mb.addMenu("文件(&F)"); f.addAction("保存参数", self._apply_params)
        f.addAction("重置参数", self._reset_params); f.addSeparator()
        f.addAction("退出(&X)", self.close)
        v=mb.addMenu("视图(&V)")
        v.addAction("显示日志", lambda: self.log_area.setVisible(True))
        v.addAction("隐藏日志", lambda: self.log_area.setVisible(False))
        mb.addMenu("帮助(&H)").addAction("关于", self._about)

    def _setup_statusbar(self):
        self.sb = QStatusBar(); self.setStatusBar(self.sb)
        self.sb_mt5 = QLabel("○ 等待连接"); self.sb_mt5.setStyleSheet("color: #7a7a9e;")
        self.sb_risk = QLabel("日: $0  回撤: 0%"); self.sb_ver = QLabel("v3.0 PySide6")
        self.sb.addWidget(self.sb_mt5)
        self.sb.addPermanentWidget(self.sb_risk)
        self.sb.addPermanentWidget(self.sb_ver)

    def _setup_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0)
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
        self.pos_side = QLabel("空仓"); self.pos_side.setStyleSheet("font-size: 14px; font-weight: bold; color: #7a7a9e;")
        self.pos_detail = QLabel("无当前持仓"); self.pos_detail.setStyleSheet("color: #7a7a9e; font-size: 13px;")
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

        self.sig_frame = self._make_card("实时信号")
        self.sig_label = QLabel("- 等待数据..."); self.sig_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #7a7a9e;")
        self.sig_bar = SignalBar(); self.sig_bar.setFixedHeight(32)
        self.sig_text = QLabel("共振: -/-  |  引擎: ~"); self.sig_text.setStyleSheet("color: #7a7a9e; font-size: 13px;")
        self.sig_frame.layout().addWidget(self.sig_label)
        self.sig_frame.layout().addWidget(self.sig_bar)
        self.sig_frame.layout().addWidget(self.sig_text)
        ml.addWidget(self.sig_frame)

        hf = QFrame(); hf.setStyleSheet(f"background: {CARD}; border-radius: 6px; padding: 8px 12px;")
        hr = QHBoxLayout(hf); hr.setContentsMargins(0,0,0,0)
        ic = QLabel("🧠"); ic.setStyleSheet("font-size: 18px;"); hr.addWidget(ic)
        self.hmm_label = QLabel("HMM: 加载中..."); self.hmm_label.setStyleSheet("color: #c0c0cc; font-size: 12px;")
        hr.addWidget(self.hmm_label); hr.addStretch()
        self.hmm_conf = QLabel(""); self.hmm_conf.setStyleSheet("color: #7a7a9e; font-size: 12px;")
        hr.addWidget(self.hmm_conf); ml.addWidget(hf); self.hmm_frame = hf

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
        bt.clicked.connect(lambda: self.detail_frame.setVisible(not self.detail_frame.isVisible()))
        ml.addWidget(bt)

        # 参数面板
        self.param_group = self._make_card("策略参数"); self.param_widgets = {}
        def ap(rl, lt, k, w=50):
            lb = QLabel(lt); lb.setStyleSheet("color: #7a7a9e; font-size: 13px;")
            ed = QLineEdit(str(self.params.get(k, DEFAULT_PARAMS.get(k,""))))
            ed.setFixedWidth(w); ed.setStyleSheet("padding: 4px 6px; font-size: 14px;")
            rl.addWidget(lb); rl.addWidget(ed); self.param_widgets[k] = ed
        r1 = QHBoxLayout()
        for kk in [("sl_atr_mult","止损ATR×"),("sl_min","止损≥$",55),("lot_fixed","固定手数",50),("risk_per_trade","风险$",45),("trail_profit","追$",40),("trail_dist","→$",50)]:
            ap(r1, kk[1], kk[0], kk[2] if len(kk)>2 else 50)
        r1.addStretch(); self.param_group.layout().addLayout(r1)
        r2 = QHBoxLayout()
        for kk in [("tp_atr_mult","止盈ATR×"),("tp_min","止盈≥$",55),("profit_lock_trigger","盈利锁$",45),("profit_lock_pullback","利润回落%",55)]:
            ap(r2, kk[1], kk[0], kk[2] if len(kk)>2 else 50)
        r2.addStretch(); self.param_group.layout().addLayout(r2)
        r3 = QHBoxLayout()
        for kk in [("resonance_threshold","共振≥",40),("cooldown_minutes","冷却m",40),("no_trade_after_hour","截止h",40),("no_trade_before_hour","起始h",40),("max_daily_loss","日亏≤$",55),("max_drawdown_pct","回撤≤%",45)]:
            ap(r3, kk[1], kk[0], kk[2] if len(kk)>2 else 50)
        r3.addStretch(); self.param_group.layout().addLayout(r3)
        r4 = QHBoxLayout()
        for kk in [("atr_spike_mult","ATR飙升×",45),("max_spread_pct","点差≤%",45)]:
            ap(r4, kk[1], kk[0], kk[2] if len(kk)>2 else 50)
        r4.addStretch(); self.param_group.layout().addLayout(r4)
        br = QHBoxLayout()
        ba = QPushButton("应用"); ba.setStyleSheet("background: #00a86b; color: white; padding: 4px 16px; font-weight: bold;"); ba.clicked.connect(self._apply_params)
        br.addWidget(ba)
        bt2 = QPushButton("重置"); bt2.setStyleSheet("background: #333366; color: #7a7a9e; padding: 4px 16px;"); bt2.clicked.connect(self._reset_params)
        br.addWidget(bt2); br.addStretch(); self.param_group.layout().addLayout(br)
        self.param_group.setVisible(False)
        self.param_toggle = QPushButton("⚙ 参数设置 ▼"); self.param_toggle.setStyleSheet("background: #15152a; color: #4dabf7; border: none; font-size: 13px; padding: 5px;")
        self.param_toggle.clicked.connect(lambda: self.param_group.setVisible(not self.param_group.isVisible()))
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
        CATEGORIES = {
            "🏆 贵金属": ["XAUUSD","XAGUSD"],
            "📊 指数":   ["US30","NAS100","SPX500","HK50"],
            "💱 外汇":   ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","NZDUSD"],
            "🛢️ 商品":   ["USOIL","UKOIL","BTCUSD"],
        }
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
        bar.addWidget(self._sel_btn); bar.addStretch()
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
        sp = SYMBOL_PARAMS.get(new_sym, {})
        for k, v in sp.items(): self.params[k] = v
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

    def _hot_reload(self):
        """热重载: 加载参数+重载模块. 代码修改需重启自动交易生效"""
        import importlib, types
        was_auto = self.auto_enabled
        if was_auto:
            self.auto_enabled = False; time.sleep(0.5)  # 让旧循环退出

        self.params = load_params()
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
        self._start_update_timer()

    def _start_update_timer(self):
        self._update_timer = QTimer(); self._update_timer.timeout.connect(self._trigger_fetch)
        self._update_timer.start(5000); self._trigger_fetch()

    def _trigger_fetch(self):
        if self._fetch_busy: return
        self._fetch_busy = True
        threading.Thread(target=self._fetch_and_update, daemon=True).start()

    def _fetch_and_update(self):
        try:
            data, ml, resonance, filter_info = fetch_all_mt5_data(self.params, self.symbol)
            if self.symbol in self._hmm_symbols:
                try:
                    from hmm_state import predict_current_state
                    self._hmm_state = predict_current_state(self.symbol)
                except Exception as e:
                    self._hmm_state = {"state":-1,"label":f"错误:{e}","confidence":0}; self.signals.log_msg.emit(f"⚠ HMM异常: {e}")
                else:
                    hmm = self._hmm_state
                    if hmm.get("state",-1) >= 0:
                        key = f"{hmm.get('state')}_{hmm.get('label')}"
                        if key != self._last_hmm_log:
                            self._last_hmm_log = key
                            self.signals.log_msg.emit(f"🧠 HMM: {hmm['label']} (置信度{hmm['confidence']:.0%})")
            self.signals.update_ui.emit(data, ml, resonance, filter_info or {})
        except Exception as e:
            self.signals.log_msg.emit(f"数据异常: {e}")
        finally:
            self._fetch_busy = False

    def _update_ui(self, data, ml, resonance, filter_info):
        try:
            self._cached_data = data; self._cached_ml = ml
            if resonance and len(resonance) > 0:
                self._cached_resonance = resonance; self._resonance_fail_count = 0
            else:
                self._resonance_fail_count += 1
                if self._resonance_fail_count > 3: self._cached_resonance = None

            p = data.get("price", 0)
            if p:
                self.price_big.setText(f"$ {p:,.2f}")
                self.price_sub.setText(f"Bid: ${p:,.2f}  Ask: ${data.get('ask',0):,.2f}")
                self.sb_mt5.setText("● 已连接"); self.sb_mt5.setStyleSheet("color: #00d26a;")

            pos = data.get("position")
            if pos:
                self._has_position = True; self._position_side = pos["side"]
                pnl = pos["profit"]; pc = GREEN if pnl >= 0 else RED
                self.pos_side.setText("📈 多" if pos["side"]=="多" else "📉 空")
                self.pos_side.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {pc};")
                self.pos_detail.setText(f"入场: ${pos['entry']:,.0f}  |  手数: {pos['volume']}  |  {'+' if pnl>=0 else ''}${pnl:.2f}")
                self.pos_detail.setStyleSheet(f"color: {pc}; font-size: 13px;")
            else:
                self._has_position = False; self._position_side = None
                self.pos_side.setText("空仓"); self.pos_side.setStyleSheet("font-size: 16px; font-weight: bold; color: #7a7a9e;")
                self.pos_detail.setText("无当前持仓"); self.pos_detail.setStyleSheet("color: #7a7a9e; font-size: 13px;")

            self.bal_label.setText(f"余额: ${data.get('balance',0):,.2f}")
            self.equity_label.setText(f"净值: ${data.get('equity',0):,.2f}")
            broker = data.get("broker",""); login = data.get("login","")
            if broker: self.broker_label.setText(f"券商: {broker}")
            if login: self.login_label.setText(f"账号: {login}")

            if data.get("balance"): self.signals.update_risk.emit(get_daily_pnl(data["balance"]))

            rd = resonance if resonance and len(resonance)>0 else self._cached_resonance or []
            buys = sum(1 for r in rd if r.get("signal")==1); sells = sum(1 for r in rd if r.get("signal")==-1)
            total = len(rd)
            if total > 0:
                res_pct = (buys/total*100) if buys>=sells else -(sells/total*100); direction = 1 if buys>=sells else -1
            else:
                res_pct=0; direction=0
            abs_pct = abs(res_pct)
            if abs_pct > 95: abs_pct=95; res_pct=95 if direction==1 else -95
            ml_dir = ml.get("signal",0) if ml.get("ready") else 0
            ml_conf = ml.get("confidence",0)*100 if ml.get("ready") else 0

            if res_pct >= 67: txt, clr = "◆ 强烈看多", GREEN
            elif res_pct <= -67: txt, clr = "◆ 强烈看空", RED
            elif res_pct >= 34: txt, clr = "◇ 偏多", "#88cc88"
            elif res_pct <= -34: txt, clr = "◇ 偏空", "#cc8888"
            else: txt, clr = "- 观望", GRAY

            ed = "看多" if ml_dir==1 else ("看空" if ml_dir==-1 else "")
            ep = f"  引擎{ed}{ml_conf:.0f}%" if ml_dir and ed else ""
            conflict = direction and ml_dir and direction != ml_dir
            if ep: txt += ep
            if conflict: txt += "  ⚠ 信号分歧"; clr = "#ff6b6b"
            self.sig_label.setText(txt); self.sig_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {clr};")

            st = f"共振 {buys}多/{sells}空  |  引擎: {ed}{ml_conf:.0f}%"
            if conflict: st += "  |  ⚠信号分歧"
            self.sig_text.setText(st)

            if direction: self.sig_bar.set_value(res_pct, clr, f"看{'多' if direction==1 else '空'} {abs_pct:.0f}%")
            else: self.sig_bar.set_value(0, GRAY, "")

            # HMM
            hmm = self._hmm_state
            if hmm and hmm["state"] >= 0:
                hl = hmm["label"]; hc = hmm["confidence"]
                cols = {"📈 强势趋势":"#00cc80","📉 高波回撤":"#e07080","📊 窄幅整理":"#e0a800"}
                c = cols.get(hl,"#7a7a9e")
                durable = 1/(1-hmm["self_prob"]) if hmm["self_prob"]<1 else 99
                self.hmm_label.setText(f"HMM: {hl}")
                self.hmm_label.setStyleSheet(f"color: {c}; font-size: 12px;")
                self.hmm_conf.setText(f"置信度 {hc:.0%} | 预计持续 {durable:.0f}根H4")
                self.hmm_frame.setVisible(True)
            else:
                self.hmm_frame.setVisible(False)

            # 按钮
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

            # 详情
            nm = {"1h":"脉冲层","4h":"谐波段","1d":"基频面"}
            rd2 = []
            if ml.get("ready"):
                ms = ml["signal"]; mc = ml["confidence"]*100
                rd2.append(("核心引擎","▲做多" if ms==1 else "▼做空",f"{mc:.0f}%",mc,GREEN if ms==1 else RED))
            for r in rd:
                sig = r.get("signal",0); dt = "▲做多" if sig==1 else ("▼做空" if sig==-1 else "-观望")
                rv = r.get('rsi',0)
                bp = max(0,min(100,(rv-50)/20*100 if sig==1 else (50-rv)/20*100)) if sig else 0
                bc = GREEN if sig==1 else (RED if sig==-1 else GRAY)
                rd2.append((nm.get(r.get("name",""),r.get("name","")),dt,f"{rv:.0f}",bp,bc))
            for label,dt,pct_t,bp,bc in rd2:
                if label in self.detail_rows:
                    ds,dp,bar = self.detail_rows[label]
                    ds.setText(dt); cl2 = GREEN if '多' in dt else (RED if '空' in dt else '#e0e0e0')
                    ds.setStyleSheet(f"color: {cl2}; font-weight: bold; font-size: 12px;")
                    dp.setText(pct_t); bar.set_value(bp,bc)
        except: pass

    def _update_risk_status(self, daily):
        pnl = daily.get("pnl",0); bal = daily.get("balance",0)
        start = daily.get("start_balance",bal) or 1
        dd_pct = (start-bal)/start*100
        self.sb_risk.setText(f"日: {'+' if pnl>=0 else ''}${pnl:.0f}  回撤: {dd_pct:.1f}%")

    def _apply_params(self):
        for k, w in self.param_widgets.items():
            try: self.params[k] = float(w.text())
            except: pass
        save_params(self.params); self.log("参数已保存")

    def _reset_params(self):
        global DEFAULT_PARAMS
        self.params = dict(DEFAULT_PARAMS)
        for k, w in self.param_widgets.items():
            w.setText(str(self.params.get(k,DEFAULT_PARAMS.get(k,""))))
        self.log("参数已重置")

    def _about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(self, "关于", "BTC AI 交易面板 v3\n多品种量化交易教学工具\n#60107268")

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
        self.sig_label.setToolTip("综合信号: 多时间框架共振+引擎判断\n强烈看多/空: >=67% 共振\n偏多/空: 34~66% 共振\n观望: <34% 或方向不明\n信号分歧: 共振和引擎方向相反, 风险大不自动开仓")
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
        self.sb_mt5.setToolTip("MT5连接状态\n已连接=MT5终端正常运行\n等待连接=MT5未启动或连接断开")
        self.sb_risk.setToolTip("日盈亏: 当日累计盈利/亏损\n回撤: 从当日最高净值下跌的百分比\n日亏或回撤超限将自动停止交易")
        self.log_area.setToolTip("交易日志, 记录所有开平仓/止损止盈/风控/异常")
        self.param_toggle.setToolTip("展开/收起策略参数面板")
        self._sel_btn.setToolTip("点击展开品类菜单选择交易品种")
        for cat, syms in self._cat_map.items():
            for sym in syms:
                pass  # tooltips via menu items

    def _auto_trade_loop(self):
        _last_trade_time = datetime(2000,1,1)
        _entry = 0; _trail = 0; _peak_profit = 0
        _last_trail_mod = 0; _last_trail_price = 0
        while self.auto_enabled:
            try:
                now = datetime.now()
                # 每轮都从文件重新加载参数, 改参数不用重启
                self.params = load_params()
                thresh = int(self.params.get("resonance_threshold",2))
                cooldown = int(self.params.get("cooldown_minutes",5))
                max_daily = float(self.params.get("max_daily_loss",300))
                dd_max = float(self.params.get("max_drawdown_pct",30))
                atr_spike = float(self.params.get("atr_spike_mult",2))
                spread_max = float(self.params.get("max_spread_pct",0.3))
                tp_atr = float(self.params.get("tp_atr_mult",2))
                sl_atr = float(self.params.get("sl_atr_mult",1.5))
                tp_min = float(self.params.get("tp_min",25))
                sl_min = float(self.params.get("sl_min",12))
                profit_lock_trigger = float(self.params.get("profit_lock_trigger",5))
                profit_lock_pullback = float(self.params.get("profit_lock_pullback",20))

                daily = get_daily_pnl(self._cached_data.get("balance", 0))
                if daily.get("pnl", 0) <= -max_daily:
                    self.log(f"自动: 日亏${abs(daily['pnl']):.0f} >= ${max_daily}, 暂停"); time.sleep(300); continue

                if not _mt5_lock.acquire(timeout=10): time.sleep(5); continue
                has_position = False
                try:
                    mt5.symbol_select(self.symbol, True)
                    tick = mt5.symbol_info_tick(self.symbol)
                    if not tick: time.sleep(5); continue
                    price = tick.bid or 0

                    pos = mt5.positions_get(symbol=self.symbol)
                    if pos:
                        has_position = True
                        p = pos[0]; current_sl = p.sl or 0; current_tp = p.tp or 0
                        pnl = p.profit; side = "BUY" if p.type==0 else "SELL"

                        # 盈利回撤保护 (回落百分比)
                        if pnl > profit_lock_trigger:
                            _peak_profit = max(_peak_profit, pnl)
                            pullback_pct = (_peak_profit - pnl) / _peak_profit * 100 if _peak_profit > 0 else 0
                            if pullback_pct >= profit_lock_pullback:
                                self.log(f"自动: 利润回落{pullback_pct:.0f}%, 平仓")
                                execute_trade("CLOSE", self.symbol)
                                _last_trade_time = now; _peak_profit = 0

                        # 移动止损
                        now_ts = time.time()
                        if now_ts - _last_trail_mod >= 60:
                            tr_dist = float(self.params.get("trail_dist", 200))
                            if side=="BUY":
                                new_sl = price - tr_dist
                                if new_sl > current_sl + 50 and abs(new_sl - _last_trail_price) > 20:
                                    _last_trail_price = new_sl; _last_trail_mod = now_ts
                                    threading.Thread(target=self._modify_sl, args=(p.ticket,new_sl), daemon=True).start()
                            else:
                                new_sl = price + tr_dist
                                if current_sl==0 or new_sl < current_sl - 50:
                                    if abs(new_sl - _last_trail_price) > 20:
                                        _last_trail_price = new_sl; _last_trail_mod = now_ts
                                        threading.Thread(target=self._modify_sl, args=(p.ticket,new_sl), daemon=True).start()
                finally:
                    try: _mt5_lock.release()
                    except: pass

                if has_position:
                    time.sleep(60); continue

                # 无持仓，检查信号开仓
                if (now - _last_trade_time).total_seconds() < cooldown*60:
                    time.sleep(30); continue

                # 交易时间过滤（过夜费保护）
                time_ok, time_reason = is_trade_time_allowed(self.params)
                if not time_ok:
                    self.log(f"自动: {time_reason}"); time.sleep(300); continue

                res = getattr(self, '_cached_resonance', None)
                if not res: time.sleep(30); continue

                buys = sum(1 for r in res if r.get("signal")==1)
                sells = sum(1 for r in res if r.get("signal")==-1)

                if buys >= thresh:
                    hmm_s = self._hmm_state.get("state",-1)
                    if self.symbol in self._hmm_symbols and hmm_s == 2:
                        self.log("自动: HMM高波回撤, 跳过开多"); time.sleep(60); continue
                    self.log(f"自动: 共振{buys}/3看涨, 开多")
                    execute_trade("BUY", self.symbol); _last_trade_time = now
                elif sells >= thresh:
                    hmm_s = self._hmm_state.get("state",-1)
                    if self.symbol in self._hmm_symbols and hmm_s == 1:
                        self.log("自动: HMM强势趋势, 跳过开空"); time.sleep(60); continue
                    self.log(f"自动: 共振{sells}/3看跌, 开空")
                    execute_trade("SELL", self.symbol); _last_trade_time = now

                time.sleep(120)
            except Exception as e:
                self.log(f"自动异常: {e}"); time.sleep(30)

    def _modify_sl(self, ticket, new_sl):
        try:
            if not _mt5_lock.acquire(timeout=5): return
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "sl": new_sl, "symbol": self.symbol}
            mt5.order_send(request)
        except: pass
        finally:
            try: _mt5_lock.release()
            except: pass

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    QToolTip.setFont(QFont("Microsoft YaHei", 9))
    p = app.palette()
    p.setColor(QPalette.ToolTipBase, QColor("#1a1a2e"))
    p.setColor(QPalette.ToolTipText, QColor("#b0b0c0"))
    app.setPalette(p)
    window = MainWindow(); window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
