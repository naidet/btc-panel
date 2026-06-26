"""
BTC AI Trading System - Core Trading Module (Production Version)
提供: MT5接口、信号计算、风控、交易执行
!!! 实盘使用前必须用模拟盘测试 !!!
"""

from datetime import datetime, time as dt_time
from typing import Optional, Dict, List, Tuple
import json, os, time, threading, warnings, math
warnings.filterwarnings("ignore", category=FutureWarning)
from btc_trader import calc_ema, calc_rsi, calc_atr, calc_adx, Bar
import MetaTrader5 as mt5
import numpy as np

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

# ============================================================
# MT5 连接管理器 (全局单例, 避免反复初始化/关闭)
# ============================================================
_mt5_initialized = False
_mt5_lock = threading.RLock()  # 可重入锁, 避免死锁
_mt5_last_ok = 0.0             # 最后一次成功操作的时间戳
_mt5_fail_count = 0            # 连续失败计数
_mt5_max_fails = 3             # 连续失败N次后强制重连
_mt5_ping_interval = 30.0      # 心跳间隔(秒)

def mt5_ensure():
    """确保MT5已初始化且连接可用, 返回True/False"""
    global _mt5_initialized, _mt5_fail_count, _mt5_last_ok

    # 快速路径：已初始化 + 最近有心跳 = 直接返回
    if _mt5_initialized and (time.time() - _mt5_last_ok) < _mt5_ping_interval:
        return True

    # 慢路径：检查连接是否真的可用
    if _mt5_initialized:
        try:
            # 真实心跳：用account_info()验证连接不是僵尸
            acct = mt5.account_info()
            if acct is not None:
                _mt5_last_ok = time.time()
                _mt5_fail_count = 0
                return True
        except:
            pass

        # 连接是僵尸，强制重连
        _mt5_fail_count += 1
        if _mt5_fail_count >= _mt5_max_fails:
            _mt5_initialized = False  # 标记失效，触发重连

    # 初始化/重连
    try:
        if mt5.initialize(path=MT5_PATH, timeout=15000):
            # 验证新连接可用
            acct = mt5.account_info()
            if acct is not None:
                _mt5_initialized = True
                _mt5_last_ok = time.time()
                _mt5_fail_count = 0
                return True
            else:
                mt5.shutdown()
                _mt5_initialized = False
    except:
        try:
            mt5.shutdown()
        except:
            pass
        _mt5_initialized = False

    _mt5_fail_count += 1
    return False

def mt5_reconnect():
    """强制断开并重新连接MT5"""
    global _mt5_initialized, _mt5_fail_count, _mt5_last_ok
    try:
        mt5.shutdown()
    except:
        pass
    _mt5_initialized = False
    _mt5_fail_count = 0
    _mt5_last_ok = 0.0
    time.sleep(0.5)  # 给MT5释放资源的时间
    return mt5_ensure()

def mt5_cleanup():
    """程序退出时调用, 关闭MT5"""
    global _mt5_initialized
    try:
        mt5.shutdown()
    except:
        pass
    _mt5_initialized = False

def _mt5_mark_ok():
    """标记一次成功的MT5操作"""
    global _mt5_last_ok, _mt5_fail_count
    _mt5_last_ok = time.time()
    _mt5_fail_count = 0

def _mt5_mark_fail():
    """标记一次失败的MT5操作"""
    global _mt5_fail_count
    _mt5_fail_count += 1

def mt5_call_with_retry(op_name, fn, retries=2, backoff=1.0):
    """
    MT5操作重试包装器
    - retries: 最多重试次数
    - backoff: 重试间隔递增倍数
    返回: (result, success)
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            with _mt5_lock:
                if not mt5_ensure():
                    last_err = "mt5_ensure 失败"
                    time.sleep(backoff * (2 ** attempt))
                    continue
                result = fn()
                _mt5_mark_ok()
                return result, True
        except Exception as e:
            last_err = str(e)[:80]
            _mt5_mark_fail()
            time.sleep(backoff * (2 ** attempt))
    return None, False

# ============================================================
# 默认参数配置
# ============================================================
DEFAULT_PARAMS = {
    "ema_period": 20,
    "rsi_period": 14,
    "rsi_long_lo": 50, "rsi_long_hi": 70,
    "rsi_short_lo": 30, "rsi_short_hi": 50,
    "adx_period": 14, "adx_threshold": 25,
    "resonance_threshold": 2,
    "sl_atr_mult": 1.5,
    "sl_min": 800,
    "tp_atr_mult": 2.0,
    "tp_min": 1500,
    "trail_profit": 5,
    "trail_dist": 300,
    "profit_lock_trigger": 5,
    "profit_lock_pullback": 20,
    "risk_per_trade": 20,
    "lot_fixed": 0,
    "lot_min": 0.01,
    "max_daily_loss": 100,
    "max_drawdown_pct": 20,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
    "cooldown_minutes": 30,
    "volatility_filter": True,
}

# ============================================================
# 品种配置
# ============================================================
SYMBOLS = ["XAUUSD", "XAGUSD"]
SYMBOL_NAMES = {"XAUUSD": "黄金", "XAGUSD": "白银"}

def _load_symbol_params(symbol: str):
    """加载品种专属配置"""
    import importlib.util
    cfg_path = os.path.join(os.path.dirname(__file__), "symbols", symbol.lower(), "config.py")
    if os.path.exists(cfg_path):
        spec = importlib.util.spec_from_file_location(f"symcfg_{symbol}", cfg_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "PARAMS", {}), getattr(mod, "STRATEGY_CFG", {})
    return {}, {}

SYMBOL_PARAMS = {}
STRATEGY_PARAMS = {}
for _sym in SYMBOLS:
    _p, _s = _load_symbol_params(_sym)
    SYMBOL_PARAMS[_sym] = _p
    STRATEGY_PARAMS[_sym] = _s

# ============================================================
# 参数持久化
# ============================================================
def load_params(filepath="panel_params.json"):
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as f:
                return {**DEFAULT_PARAMS, **json.load(f)}
        except:
            pass
    return dict(DEFAULT_PARAMS)

def save_params(params, filepath="panel_params.json"):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)

# ============================================================
# 当日盈亏追踪
# ============================================================
_daily_pnl_cache = {"date": None, "start_balance": None, "pnl": 0.0}

def get_daily_pnl() -> dict:
    """
    追踪当日盈亏, 从MT5账户读取余额, 带RLock保护
    返回: {"date", "start_balance", "pnl", "balance", "equity"}
    """
    global _daily_pnl_cache
    today = datetime.now().strftime("%Y%m%d")
    s = _daily_pnl_cache

    with _mt5_lock:
        if not mt5_ensure():
            return {"date": today, "start_balance": s.get("start_balance"),
                    "pnl": s.get("pnl", 0.0), "balance": 0, "equity": 0}
        acct = mt5.account_info()
        if not acct:
            return {"date": today, "start_balance": s.get("start_balance"),
                    "pnl": s.get("pnl", 0.0), "balance": 0, "equity": 0}

        balance = acct.balance
        equity = acct.equity

        if s["date"] != today or s["start_balance"] is None:
            s["date"] = today
            s["start_balance"] = balance
            s["pnl"] = 0.0
        else:
            s["pnl"] = balance - s["start_balance"]

        return {"date": s["date"], "start_balance": s["start_balance"],
                "pnl": s["pnl"], "balance": balance, "equity": equity}

# ============================================================
# MT5 数据获取 (使用全局连接, 带RLock)
# ============================================================
def fetch_all_mt5_data(symbol: str, include_h1: bool = True) -> Optional[dict]:
    """获取多时间框架K线数据，带重试和单周期容错"""
    def _do_one_tf(s, tf, count):
        """获取单个周期的K线，失败返回None"""
        try:
            rates = mt5.copy_rates_from_pos(s, tf, 0, count)
            if rates is not None and len(rates) > 0:
                return [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rates]
        except:
            pass
        return None

    def _do():
        mt5.symbol_select(symbol, True)
        frames = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
        }
        result = {}
        failed_tfs = []
        for name, tf in frames.items():
            if name == "H1" and not include_h1:
                continue
            bars = _do_one_tf(symbol, tf, 200)
            if bars:
                result[name] = bars
            else:
                failed_tfs.append(name)

        # 至少需要核心周期（H1/H4/D1）中2个有效
        core = ["H1", "H4", "D1"]
        core_ok = sum(1 for c in core if c in result)
        if core_ok < 2:
            raise RuntimeError(f"核心周期不足 有效:{core_ok}/{len(core)}")
        if failed_tfs:
            raise RuntimeError(f"部分周期超时: {failed_tfs}")  # 会被重试
        return result

    # 最多重试2次；重试可以恢复超时的周期
    for attempt in range(3):
        result, ok = mt5_call_with_retry(f"K线获取(尝试{attempt+1})", _do, retries=0)
        if ok and result:
            return result
        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))  # 递增等待
    return None


def fetch_dashboard_data(symbol: str, params: dict):
    """
    面板全能数据获取 — 一次调用返回面板所需的全部数据
    返回: (data_dict, ml_dict, resonance_list, filter_info_dict)

    data_dict 包含: price, ask, bid, position, balance, equity, broker, login
    ml_dict 包含:   signal, ready, confidence (简化版ML信号, 基于共振聚合)
    resonance_list: 多时间框架共振信号列表
    filter_info:    风控过滤信息
    """
    # --- 1. 基础数据 (价格/账户/持仓) ---
    data = {}
    try:
        tick, info = get_mt5_tick(symbol)
        if tick and info:
            data["price"] = tick.bid
            data["ask"] = tick.ask
            data["bid"] = tick.bid
            data["spread"] = tick.ask - tick.bid

        acct = get_mt5_account_info()
        if acct:
            data["balance"] = acct.get("balance", 0)
            data["equity"] = acct.get("equity", 0)
            data["broker"] = acct.get("server", "")
            data["login"] = str(acct.get("login", ""))

        positions = get_mt5_positions(symbol)
        if positions:
            p = positions[0]
            side = "多" if p.type == 0 else "空"
            data["position"] = {
                "side": side,
                "entry": p.price_open,
                "volume": p.volume,
                "profit": p.profit,
                "ticket": p.ticket,
            }
        else:
            data["position"] = None
    except Exception:
        pass

    # --- 2. 共振信号 ---
    # name映射: 面板详情区用 "1h"/"4h"/"1d" 匹配 脉冲层/谐波段/基频面
    _TF_NAME_MAP = {"M5": "1h", "M15": "1h", "H1": "1h", "H4": "4h", "D1": "1d"}
    resonance = []
    try:
        raw_bars = fetch_all_mt5_data(symbol, include_h1=True)
        if raw_bars:
            for tf in ["M5", "M15", "H1", "H4", "D1"]:
                if tf not in raw_bars:
                    continue
                sig = calc_signal(raw_bars[tf], params)
                resonance.append({
                    "timeframe": tf,
                    "name": _TF_NAME_MAP.get(tf, tf),   # 面板详情匹配用
                    "signal": sig["signal"],
                    "strength": sig["strength"],
                    "reasons": sig.get("reasons", []),
                    "rsi": sig.get("rsi", 50),
                    "adx": sig.get("adx", 0),
                    "atr": sig.get("atr", 0),
                })
    except Exception:
        pass

    # --- 3. ML引擎信号 (基于共振聚合, 强化过滤) ---
    ml = {"signal": 0, "ready": False, "confidence": 0.0}
    try:
        if resonance and len(resonance) >= 3:
            # 按时间框架分组: 脉冲层(1h)=M5+M15+H1, 谐波段(4h)=H4, 基频面(1d)=D1
            groups = {
                "脉冲层": [r for r in resonance if r["name"] == "1h"],
                "谐波段": [r for r in resonance if r["name"] == "4h"],
                "基频面": [r for r in resonance if r["name"] == "1d"],
            }
            
            # 每个组取信号（组内多数票）
            group_signals = {}
            for gname, rs in groups.items():
                if not rs:
                    continue
                buys = sum(1 for r in rs if r["signal"] == 1)
                sells = sum(1 for r in rs if r["signal"] == -1)
                if buys > sells:
                    group_signals[gname] = 1
                elif sells > buys:
                    group_signals[gname] = -1
                else:
                    group_signals[gname] = 0  # 平局
            
            # 层级加权 (基频面权重2, 谐波段权重1.5, 脉冲层权重1)
            weighted = {"BUY": 0.0, "SELL": 0.0}
            for gname, sig in group_signals.items():
                w = {"基频面": 2.0, "谐波段": 1.5, "脉冲层": 1.0}.get(gname, 1.0)
                if sig == 1:
                    weighted["BUY"] += w
                elif sig == -1:
                    weighted["SELL"] += w
            
            # 判断方向，要求 >1.0 加权优势
            if weighted["BUY"] > 1.0 and weighted["BUY"] > weighted["SELL"]:
                ml["signal"] = 1
                ml["confidence"] = min(0.95, weighted["BUY"] / (weighted["BUY"] + weighted["SELL"]))
            elif weighted["SELL"] > 1.0 and weighted["SELL"] > weighted["BUY"]:
                ml["signal"] = -1
                ml["confidence"] = min(0.95, weighted["SELL"] / (weighted["SELL"] + weighted["BUY"]))
            
            # 附加组信号信息给面板
            ml["group_signals"] = group_signals
            ml["ready"] = True
            
            # 强烈信号标记（当基频面和谐波段同向且脉冲层同向或中性）
            if group_signals.get("基频面") == group_signals.get("谐波段"):
                if group_signals.get("脉冲层") == group_signals.get("基频面"):
                    ml["strong"] = True
                elif group_signals.get("脉冲层") == 0:
                    ml["strong"] = True
                else:
                    ml["strong"] = False
            else:
                ml["strong"] = False
    except Exception:
        pass

    # --- 4. 过滤信息 ---
    filter_info = {}
    try:
        # 点差检查
        spread = data.get("spread", 0)
        price = data.get("price", 1)
        if price > 0 and spread > 0:
            filter_info["spread_pct"] = spread / price * 100

        # HMM状态 (直接引用全局变量)
        filter_info["hmm_state"] = _hmm_state.get("state", -1)
        filter_info["hmm_label"] = ""
        state = _hmm_state.get("state")
        if state == 0:
            filter_info["hmm_label"] = "强势趋势"
        elif state == 1:
            filter_info["hmm_label"] = "窄幅整理"
        elif state == 2:
            filter_info["hmm_label"] = "高波回撤"

        # 日盈亏
        daily = get_daily_pnl()
        filter_info["daily_pnl"] = daily.get("pnl", 0)

        # 更新HMM状态
        update_hmm_state(symbol)
    except Exception:
        pass

    return data, ml, resonance, filter_info

def get_mt5_account_info() -> Optional[dict]:
    """获取账户信息，带自动重试"""
    def _do():
        acct = mt5.account_info()
        if acct:
            return {"balance": acct.balance, "equity": acct.equity,
                    "margin": acct.margin, "free_margin": acct.margin_free,
                    "login": acct.login, "server": acct.server}
        return None
    result, ok = mt5_call_with_retry("账户查询", _do, retries=1)
    return result if ok else None

def get_mt5_positions(symbol: str = "") -> list:
    """获取持仓，带自动重试"""
    def _do():
        if symbol:
            mt5.symbol_select(symbol, True)
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        return list(positions or [])
    result, ok = mt5_call_with_retry("持仓查询", _do, retries=1)
    return result if ok else []

def get_mt5_tick(symbol: str):
    """获取最新tick，带自动重试。返回(symbol_info_tick, symbol_info)或(None, None)"""
    def _do():
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            raise RuntimeError("tick/info为None")
        return (tick, info)
    result, ok = mt5_call_with_retry("报价获取", _do, retries=2)
    return result if ok else (None, None)

# ============================================================
# 信号计算
# ============================================================
def calc_signal(bars: List[Bar], params: dict) -> dict:
    """计算单周期交易信号"""
    if not bars or len(bars) < 30:
        return {"signal": 0, "strength": 0, "reasons": ["数据不足"]}
    closes = np.array([b.close for b in bars])
    highs = np.array([b.high for b in bars])
    lows = np.array([b.low for b in bars])
    ema = calc_ema(closes, params.get("ema_period", 20))
    rsi = calc_rsi(closes, params.get("rsi_period", 14))
    atr_list = calc_atr(highs, lows, closes, 14)
    atr = atr_list[-1] if len(atr_list) > 0 else 0.0
    adx_list = calc_adx(highs, lows, closes, params.get("adx_period", 14))
    adx = adx_list[-1] if len(adx_list) > 0 else 0.0
    last = bars[-1]
    signal = 0
    reasons = []
    if last.close > ema[-1]:
        signal += 1
        reasons.append("EMA向上")
    else:
        signal -= 1
        reasons.append("EMA向下")
    rsi_v = rsi[-1]
    if rsi_v > params.get("rsi_long_lo", 50):
        signal += 1
        reasons.append(f"RSI={rsi_v:.1f}")
    elif rsi_v < params.get("rsi_short_hi", 50):
        signal -= 1
        reasons.append(f"RSI={rsi_v:.1f}")
    if adx > params.get("adx_threshold", 25):
        reasons.append(f"ADX={adx:.1f}(强趋势)")
    return {"signal": 1 if signal > 0 else (-1 if signal < 0 else 0),
            "strength": abs(signal), "reasons": reasons,
            "rsi": rsi_v, "adx": adx, "atr": atr}

def calc_resonance(symbol: str, params: dict) -> list:
    """多时间框架共振分析, 返回各周期信号列表"""
    data = fetch_all_mt5_data(symbol, include_h1=False)
    if not data:
        return []
    result = []
    for tf in ["M5", "M15", "H1", "H4", "D1"]:
        if tf not in data:
            continue
        sig = calc_signal(data[tf], params)
        result.append({"timeframe": tf, "signal": sig["signal"],
                        "strength": sig["strength"], "reasons": sig["reasons"]})
    return result

# ============================================================
# HMM 市场状态判断
# ============================================================
_hmm_state = {"state": -1, "confidence": 0.0, "expected_duration": 0}

def update_hmm_state(symbol: str):
    """更新HMM市场状态 (简化版: 基于波动率和趋势方向)"""
    global _hmm_state
    data = fetch_all_mt5_data(symbol, include_h1=False)
    if not data or "H4" not in data:
        return
    bars = data["H4"]
    closes = np.array([b.close for b in bars[-50:]])
    if len(closes) < 30:
        return
    returns = np.diff(closes) / closes[:-1]
    vol = np.std(returns) * np.sqrt(6 * 24)
    sma20 = np.mean(closes[-20:])
    sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma20
    trend = 1 if sma20 > sma50 else -1
    hist_vols = []
    for i in range(30, len(closes)):
        h = np.std(np.diff(closes[:i]) / closes[:i-1])
        hist_vols.append(h)
    vol_threshold = np.percentile(hist_vols, 80) if len(hist_vols) > 10 else vol
    if vol > vol_threshold * 1.2:
        if trend == -1:
            _hmm_state = {"state": 2, "confidence": 0.9, "expected_duration": 8}
        else:
            _hmm_state = {"state": 0, "confidence": 0.7, "expected_duration": 12}
    else:
        _hmm_state = {"state": 1, "confidence": 0.6, "expected_duration": 20}

def get_trade_signal(symbol: str, params: dict) -> dict:
    """
    综合交易信号（供手工开仓参考）
    返回: {
        "direction": 1(做多) / -1(做空) / 0(观望),
        "strength": "强烈" / "中等" / "弱",
        "confidence": 0.0~1.0,
        "reason": "文本描述",
        "components": {  # 各组件信号
            "base": 1/-1/0,
            "harmonic": 1/-1/0, 
            "pulse": 1/-1/0,
            "hmm": 1/-1/0,
            "atr_filter": bool,
            "daily_filter": bool
        }
    }
    """
    try:
        data, ml, resonance, filter_info = fetch_dashboard_data(symbol, params)
        hmm_state = filter_info.get("hmm_state", -1)
        
        # 1. 解析组件信号
        group_sigs = ml.get("group_signals", {})
        base_sig = group_sigs.get("基频面", 0)      # 长期
        harmonic_sig = group_sigs.get("谐波段", 0)   # 中期
        pulse_sig = group_sigs.get("脉冲层", 0)      # 短期
        
        # 2. HMM信号转换 (状态->方向)
        hmm_sig = 0
        if hmm_state == 0:  # 强势趋势 → 做多
            hmm_sig = 1
        elif hmm_state == 2:  # 高波回撤 → 做空
            hmm_sig = -1
        
        # 3. 加权决策（基频面权重最高）
        weighted = {"BUY": 0.0, "SELL": 0.0}
        if base_sig == 1:
            weighted["BUY"] += 2.5
        elif base_sig == -1:
            weighted["SELL"] += 2.5
            
        if harmonic_sig == 1:
            weighted["BUY"] += 2.0
        elif harmonic_sig == -1:
            weighted["SELL"] += 2.0
            
        if pulse_sig == 1:
            weighted["BUY"] += 1.0
        elif pulse_sig == -1:
            weighted["SELL"] += 1.0
            
        if hmm_sig == 1:
            weighted["BUY"] += 1.5
        elif hmm_sig == -1:
            weighted["SELL"] += 1.5
        
        # 4. 决策 (基频面+谐波段同向就足够强)
        direction = 0
        confidence = 0.0
        strength = "弱"
        
        # 如果基频面和谐波段同向，那就是强烈信号
        if base_sig == harmonic_sig and base_sig != 0:
            direction = base_sig
            confidence = 0.8  # 基频+谐波同向就是80%置信度
        # 否则用加权总分≥3.0（更宽松）
        elif weighted["BUY"] >= 3.0 and weighted["BUY"] > weighted["SELL"]:
            direction = 1
            confidence = weighted["BUY"] / (weighted["BUY"] + weighted["SELL"])
        elif weighted["SELL"] >= 3.0 and weighted["SELL"] > weighted["BUY"]:
            direction = -1
            confidence = weighted["SELL"] / (weighted["SELL"] + weighted["BUY"])
        
        # 5. 强度判定
        if confidence >= 0.75:
            strength = "强烈"
        elif confidence >= 0.6:
            strength = "中等"
        elif confidence > 0:
            strength = "弱"
        
        # 6. 理由构建
        reasons = []
        if base_sig == 1:
            reasons.append("基频面看多")
        elif base_sig == -1:
            reasons.append("基频面看空")
            
        if harmonic_sig == 1:
            reasons.append("谐波段看多")
        elif harmonic_sig == -1:
            reasons.append("谐波段看空")
            
        if pulse_sig == 1:
            reasons.append("脉冲层看多")
        elif pulse_sig == -1:
            reasons.append("脉冲层看空")
            
        if hmm_sig == 1:
            reasons.append("HMM强势趋势")
        elif hmm_sig == -1:
            reasons.append("HMM高波回撤")
        
        # 7. 过滤条件检查（供参考）
        atr_ok = filter_info.get("spread_pct", 0) <= float(params.get("max_spread_pct", 0.15))
        daily_ok = abs(filter_info.get("daily_pnl", 0)) < abs(float(params.get("max_daily_loss", 100)))
        
        return {
            "direction": direction,
            "strength": strength,
            "confidence": confidence,
            "reason": " + ".join(reasons) if reasons else "观望",
            "components": {
                "base": base_sig,
                "harmonic": harmonic_sig,
                "pulse": pulse_sig,
                "hmm": hmm_sig,
                "atr_filter": atr_ok,
                "daily_filter": daily_ok
            },
            "weighted": weighted,
            "raw_ml": ml
        }
    except Exception as e:
        return {
            "direction": 0,
            "strength": "错误",
            "confidence": 0.0,
            "reason": f"计算错误: {e}",
            "components": {}
        }

# ============================================================
# 风险控制检查
# ============================================================
def check_risk_gates(symbol: str, side: str, params: dict) -> Tuple[bool, str]:
    """检查风控闸门, 返回(passed, reason)"""
    daily = get_daily_pnl()
    if daily.get("pnl", 0) <= -abs(float(params.get("max_daily_loss", 100))):
        return False, f"日亏${abs(daily['pnl']):.0f}超限"

    tick, info = get_mt5_tick(symbol)
    if tick and info:
        spread_pct = (tick.ask - tick.bid) / tick.bid * 100
        if spread_pct > float(params.get("max_spread_pct", 0.15)):
            return False, f"点差{spread_pct:.3f}%过高"

    with _mt5_lock:
        if mt5_ensure():
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 30)
            if rates is not None and len(rates) > 14:
                trs = []
                for i in range(1, len(rates)):
                    h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                    trs.append(max(h-l, abs(h-c), abs(l-c)))
                atr = np.mean(trs[-14:])
                atr_avg = np.mean(trs) if len(trs) >= 30 else atr
                if atr > atr_avg * float(params.get("atr_spike_mult", 2.0)):
                    return False, f"ATR飙升{atr/atr_avg:.1f}x"

    if _hmm_state.get("state") == 2 and side == "BUY":
        return False, "HMM高波回撤, 不做多"
    if _hmm_state.get("state") == 0 and side == "SELL":
        return False, "HMM强势趋势, 不做空"
    return True, ""

# ============================================================
# 交易执行 (核心函数, 带RLock, 不关闭MT5)
# ============================================================
def execute_trade(action: str, symbol: str, params: dict = None) -> dict:
    """
    执行交易指令
    action: "BUY", "SELL", "CLOSE"
    symbol: 交易品种
    params: 参数字典 (不传则自动加载)
    返回: {"ok": bool, "msg": str, ...}
    """
    if params is None:
        params = load_params()

    sym_params, _ = _load_symbol_params(symbol)

    with _mt5_lock:
        if not mt5_ensure():
            return {"ok": False, "msg": "MT5连接失败"}

        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            info = mt5.symbol_info(symbol)
            if not tick or not info:
                return {"ok": False, "msg": "无法获取报价或品种信息"}

            # ========== 平仓 ==========
            if action == "CLOSE":
                positions = mt5.positions_get(symbol=symbol)
                if not positions:
                    return {"ok": True, "msg": "无持仓"}
                for p in positions:
                    close_price = tick.bid if p.type == 0 else tick.ask
                    req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": p.symbol,
                        "volume": p.volume,
                        "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                        "position": p.ticket,
                        "price": close_price,
                        "magic": 60107,
                        "comment": "BTC-AI-CLOSE",
                        "type_filling": mt5.ORDER_FILLING_IOC
                    }
                    result = mt5.order_send(req)
                    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
                        return {"ok": False, "msg": f"平仓失败: {result.comment if result else '未知'}"}
                return {"ok": True, "msg": "已平仓"}

            # ========== 开仓 ==========
            is_buy = (action == "BUY")
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            price = tick.ask if is_buy else tick.bid

            # --- SL/TP 距离 (点数) ---
            sl_atr_mult = float(params.get("sl_atr_mult", 1.5) or sym_params.get("sl_atr_mult", 1.5))
            tp_atr_mult = float(params.get("tp_atr_mult", 2.0) or sym_params.get("tp_atr_mult", 2.0))
            sl_min_cfg = float(params.get("sl_min", 800) or sym_params.get("sl_min", 800))
            tp_min_cfg = float(params.get("tp_min", 1500) or sym_params.get("tp_min", 1500))

            # 从H4计算ATR (转换为点数)
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 20)
            sl_points = int(sl_min_cfg)
            tp_points = int(tp_min_cfg)
            if rates is not None and len(rates) > 14:
                trs = []
                for i in range(1, len(rates)):
                    h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                    trs.append(max(h-l, abs(h-c), abs(l-c)))
                atr_price = np.mean(trs[-14:])
                point = info.point
                atr_points = atr_price / point if point > 0 else atr_price * 10000
                sl_points = max(int(sl_min_cfg), int(atr_points * sl_atr_mult))
                tp_points = max(int(tp_min_cfg), int(atr_points * tp_atr_mult))

            # --- SL/TP 价格 ---
            point = info.point
            sl_price = (price - sl_points * point) if is_buy else (price + sl_points * point)
            tp_price = (price + tp_points * point) if is_buy else (price - tp_points * point)

            # --- 手数计算 ---
            lot_fixed = float(params.get("lot_fixed", 0) or sym_params.get("lot_fixed", 0))
            lot_min = max(float(params.get("lot_min", 0.01) or sym_params.get("lot_min", 0.01)),
                         info.volume_min or 0.01)

            if lot_fixed > 0:
                lot = lot_fixed
            else:
                risk = float(params.get("risk_per_trade", 20) or sym_params.get("risk_per_trade", 20))
                point_value = point * price  # 1点的价格价值 (近似)
                risk_per_point = point_value * (info.trade_contract_size or 1)
                if risk_per_point > 0 and sl_points > 0:
                    lot = risk / (sl_points * risk_per_point)
                else:
                    lot = lot_min
                lot = max(lot_min, round(lot, 2))

            lot = max(lot_min, min(lot, info.volume_max or 100))
            lot = math.floor(lot * 100) / 100  # 向下取整到0.01手

            # --- 发送订单 ---
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "magic": 60107,
                "comment": "BTC-AI-OPEN",
                "type_filling": mt5.ORDER_FILLING_IOC
            }
            result = mt5.order_send(req)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {"ok": True,
                        "msg": f"开仓成功 {action} {lot}手 SL:{sl_price:.5f} TP:{tp_price:.5f}",
                        "ticket": result.order, "sl": sl_price, "tp": tp_price,
                        "sl_points": sl_points, "tp_points": tp_points}
            else:
                err = result.comment if result else "未知错误"
                return {"ok": False, "msg": f"开仓失败: {err}"}
        except Exception as e:
            return {"ok": False, "msg": f"执行异常: {e}"}

# ============================================================
# 修改SL (移动止损用)
# ============================================================
def modify_sl(ticket: int, new_sl: float) -> bool:
    """修改持仓止损价, 带重试"""
    def _do():
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
        p = positions[0]
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": p.ticket,
            "symbol": p.symbol,
            "sl": new_sl,
            "tp": p.tp,
            "magic": 60107
        }
        result = mt5.order_send(req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"SL修改失败: {result.comment if result else '无响应'}")
        return True
    result, ok = mt5_call_with_retry("止损修改", _do, retries=2, backoff=1.5)
    return result if ok else False

# ============================================================
# 交易时间过滤
# ============================================================
def is_trade_time_allowed(params: dict) -> Tuple[bool, str]:
    """检查当前是否在允许交易的时间段内 (已关闭时间限制)"""
    # 注释掉原有的时间限制逻辑，永远允许交易
    # now = datetime.now()
    # after_hour = int(params.get("no_trade_after_hour", 22))
    # before_hour = int(params.get("no_trade_before_hour", 0))
    # current_hour = now.hour
    # if current_hour >= after_hour:
    #     return False, f"已过{after_hour}点, 停止开仓(避免过夜费)"
    # if 0 < before_hour <= current_hour:
    #     return False, f"未到{before_hour}点, 不允许开仓"
    return True, "交易时间限制已关闭"
