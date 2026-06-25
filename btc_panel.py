"""
BTC AI Trading System - Core Trading Module
Provides: MT5 interface, signal calculation, risk management, trade execution
"""
from datetime import datetime, time as dt_time
from typing import Optional, Dict, List
import json, os, time, threading, warnings, math
warnings.filterwarnings("ignore", category=FutureWarning)
from btc_trader import calc_ema, calc_rsi, calc_atr, calc_adx, Bar
import MetaTrader5 as mt5
import numpy as np

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

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
    "trail_profit": 3,
    "trail_dist": 200,
    "profit_lock_trigger": 5,
    "profit_lock_pullback": 20,
    "risk_per_trade": 20,
    "lot_fixed": 0,
    "lot_min": 0.01,
    "max_daily_loss": 500,
    "max_drawdown_pct": 20,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
    "cooldown_minutes": 15,
    "volatility_filter": True,
    "no_trade_after_hour": 22,
    "no_trade_before_hour": 0,
}

# ============================================================
# 品种配置
# ============================================================
SYMBOLS = ["BTCUSD", "XAUUSD", "XAGUSD"]
SYMBOL_NAMES = {"BTCUSD": "BTC", "XAUUSD": "黄金", "XAGUSD": "白银"}

def _load_symbol_params(symbol: str) -> dict:
    """加载品种专属配置，回退到 symbols/<sym>/config.py"""
    import importlib.util, sys
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
            with open(filepath) as f:
                return {**DEFAULT_PARAMS, **json.load(f)}
        except: pass
    return dict(DEFAULT_PARAMS)

def save_params(params, filepath="panel_params.json"):
    with open(filepath, "w") as f:
        json.dump(params, f, indent=2)

# ============================================================
# MT5 线程锁
# ============================================================
_mt5_lock = threading.Lock()

# ============================================================
# 当日盈亏追踪
# ============================================================
_daily_pnl_state = {"date": None, "start_balance": None, "pnl": 0.0}

def get_daily_pnl() -> dict:
    """追踪当日盈亏，自动从MT5读取余额"""
    today = datetime.now().strftime("%Y%m%d")
    s = _daily_pnl_state
    if not mt5.initialize(path=MT5_PATH):
        return {"date": today, "start_balance": s.get("start_balance"), "pnl": s.get("pnl", 0.0)}
    acct = mt5.account_info()
    mt5.shutdown()
    if not acct:
        return {"date": today, "start_balance": s.get("start_balance"), "pnl": s.get("pnl", 0.0)}
    balance = acct.balance
    if s["date"] != today or s["start_balance"] is None:
        s["date"] = today
        s["start_balance"] = balance
        s["pnl"] = 0.0
    else:
        s["pnl"] = balance - s["start_balance"]
    return {"date": s["date"], "start_balance": s["start_balance"], "pnl": s["pnl"], "balance": balance}

# ============================================================
# MT5 数据获取
# ============================================================
def fetch_all_mt5_data(symbol: str, include_h1: bool = True) -> Optional[dict]:
    """获取多时间框架K线数据，返回各周期Bar列表"""
    if not mt5.initialize(path=MT5_PATH):
        return None
    try:
        frames = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
        }
        result = {}
        for name, tf in frames.items():
            if name == "H1" and not include_h1:
                continue
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 200)
            if rates is not None:
                bars = [Bar(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rates]
                result[name] = bars
        return result
    finally:
        mt5.shutdown()

def get_mt5_account_info() -> Optional[dict]:
    """获取账户信息"""
    if not mt5.initialize(path=MT5_PATH):
        return None
    try:
        acct = mt5.account_info()
        if acct:
            return {"balance": acct.balance, "equity": acct.equity,
                    "margin": acct.margin, "free_margin": acct.margin_free,
                    "login": acct.login, "server": acct.server}
        return None
    finally:
        mt5.shutdown()

def get_mt5_positions(symbol: str = "") -> list:
    """获取当前持仓"""
    if not mt5.initialize(path=MT5_PATH):
        return []
    try:
        if symbol:
            return list(mt5.positions_get(symbol=symbol) or [])
        return list(mt5.positions_get() or [])
    finally:
        mt5.shutdown()

# ============================================================
# 信号计算
# ============================================================
def calc_signal(bars: List[Bar], params: dict) -> dict:
    """计算单周期交易信号"""
    if not bars or len(bars) < 30:
        return {"signal": 0, "reason": "数据不足"}
    closes = np.array([b.close for b in bars])
    ema = calc_ema(closes, params.get("ema_period", 20))
    rsi = calc_rsi(closes, params.get("rsi_period", 14))
    atr = calc_atr(bars, 14)
    adx = calc_adx(bars, params.get("adx_period", 14))
    last = bars[-1]
    signal = 0; reasons = []
    if last.close > ema[-1]:
        signal += 1; reasons.append("EMA向上")
    else:
        signal -= 1; reasons.append("EMA向下")
    rsi_v = rsi[-1]
    if rsi_v > params.get("rsi_long_lo", 50):
        signal += 1; reasons.append(f"RSI={rsi_v:.1f}")
    elif rsi_v < params.get("rsi_short_hi", 50):
        signal -= 1; reasons.append(f"RSI={rsi_v:.1f}")
    if adx[-1] > params.get("adx_threshold", 25):
        reasons.append(f"ADX={adx[-1]:.1f}(强趋势)")
    return {"signal": 1 if signal > 0 else (-1 if signal < 0 else 0),
            "strength": abs(signal), "reasons": reasons,
            "rsi": rsi_v, "adx": adx[-1], "atr": atr}

def calc_resonance(symbol: str, params: dict) -> list:
    """多时间框架共振分析"""
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
    """更新HMM市场状态（简化版：基于波动率和趋势）"""
    global _hmm_state
    data = fetch_all_mt5_data(symbol, include_h1=False)
    if not data or "H4" not in data:
        return
    bars = data["H4"]
    closes = np.array([b.close for b in bars[-50:]])
    returns = np.diff(closes) / closes[:-1]
    vol = np.std(returns) * np.sqrt(6 * 24)  # 年化波动率
    sma20 = np.mean(closes[-20:])
    sma50 = np.mean(closes[-50:])
    trend = 1 if sma20 > sma50 else -1
    if vol > np.percentile([np.std(np.diff(closes[-100:i]) / closes[-100:i-1]) for i in range(50, len(closes))], 80):
        if trend == -1:
            _hmm_state = {"state": 2, "confidence": 0.9, "expected_duration": 8}  # 高波回撤
        else:
            _hmm_state = {"state": 0, "confidence": 0.7, "expected_duration": 12}  # 强势趋势
    else:
        _hmm_state = {"state": 1, "confidence": 0.6, "expected_duration": 20}  # 窄幅整理

def get_hmm_state() -> dict:
    return dict(_hmm_state)

# ============================================================
# 风险控制
# ============================================================
def check_risk_gates(symbol: str, side: str, params: dict) -> tuple:
    """检查风控闸门，返回 (passed: bool, reason: str)"""
    # 日亏检查
    daily = get_daily_pnl()
    if daily["pnl"] <= -params.get("max_daily_loss", 500):
        return False, f"日亏${abs(daily['pnl']):.0f}超限"
    # 点差检查
    if not mt5.initialize(path=MT5_PATH):
        return False, "MT5连接失败"
    try:
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick and info:
            spread_pct = (tick.ask - tick.bid) / tick.bid * 100
            if spread_pct > params.get("max_spread_pct", 0.15):
                return False, f"点差{spread_pct:.3f}%过高"
        # ATR飙升检查
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 30)
        if rates is not None and len(rates) > 14:
            trs = []
            for i in range(1, len(rates)):
                h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                trs.append(max(h-l, abs(h-c), abs(l-c)))
            atr = np.mean(trs[-14:])
            atr_avg = np.mean(trs[-30:]) if len(trs) >= 30 else atr
            if atr > atr_avg * params.get("atr_spike_mult", 2.0):
                return False, f"ATR飙升{atr/atr_avg:.1f}x"
    finally:
        mt5.shutdown()
    # HMM过滤
    hmm = get_hmm_state()
    if hmm["state"] == 2 and side == "BUY":
        return False, "HMM高波回撤，不做多"
    if hmm["state"] == 0 and side == "SELL":
        return False, "HMM强势趋势，不做空"
    return True, ""

# ============================================================
# 交易执行
# ============================================================
def execute_trade(action: str, symbol: str, params: dict = None, sl: float = 0, tp: float = 0) -> dict:
    """执行交易指令，返回结果字典"""
    if params is None:
        params = load_params()
    sym_params, _ = _load_symbol_params(symbol)
    lot_fixed = params.get("lot_fixed", 0) or sym_params.get("lot_fixed", 0)
    lot_min = params.get("lot_min", 0.01) or sym_params.get("lot_min", 0.01)
    risk = params.get("risk_per_trade", 20) or sym_params.get("risk_per_trade", 20)

    if not mt5.initialize(path=MT5_PATH):
        return {"ok": False, "msg": "MT5连接失败"}
    try:
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"ok": False, "msg": "无法获取报价"}
        price = tick.ask if action == "BUY" else tick.bid
        # 刷新价格避免过期
        tick2 = mt5.symbol_info_tick(symbol)
        if tick2:
            price = tick2.ask if action == "BUY" else tick2.bid

        if action == "CLOSE":
            positions = mt5.positions_get(symbol=symbol)
            if not positions:
                return {"ok": True, "msg": "无持仓"}
            for p in positions:
                tick = mt5.symbol_info_tick(p.symbol)
                close_price = tick.bid if p.type == 0 else tick.ask
                req = {"action": mt5.TRADE_ACTION_DEAL,
                       "symbol": p.symbol,
                       "volume": p.volume,
                       "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                       "position": p.ticket,
                       "price": close_price,
                       "magic": 60107,
                       "comment": "BTC-AI-CLOSE",
                       "type_filling": mt5.ORDER_FILLING_IOC}
                mt5.order_send(req)
            return {"ok": True, "msg": "已平仓"}

        # 开仓
        is_buy = action == "BUY"
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        # 计算SL/TP距离
        info = mt5.symbol_info(symbol)
        pip_mult = 10 ** (info.digits or 5) / 10 ** (info.digits or 5) * 10 if info else 1
        # ATR止损
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 20)
        sl_dist = params.get("sl_min", 800)
        tp_dist = params.get("tp_min", 1500)
        if rates is not None and len(rates) > 14:
            trs = []
            for i in range(1, len(rates)):
                h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                trs.append(max(h-l, abs(h-c), abs(l-c)))
            atr = np.mean(trs[-14:])
            sl_dist = max(sl_dist, int(atr * params.get("sl_atr_mult", 1.5)))
            tp_dist = max(tp_dist, int(atr * params.get("tp_atr_mult", 2.0)))
        sl_price = (price - sl_dist * pip_mult if is_buy else price + sl_dist * pip_mult) if sl > 0 else 0
        tp_price = (price + tp_dist * pip_mult if is_buy else price - tp_dist * pip_mult) if tp > 0 else 0
        # 手数
        if lot_fixed > 0:
            lot = lot_fixed
        else:
            lot = max(lot_min, round(risk / sl_dist, 2)) if sl_dist > 0 else lot_min
        lot = max(lot_min, lot)
        # 确保MT5最小手数
        lot = max(info.volume_min or 0.01, lot)

        req = {"action": mt5.TRADE_ACTION_DEAL,
               "symbol": symbol,
               "volume": lot,
               "type": order_type,
               "price": price,
               "sl": sl_price,
               "tp": tp_price,
               "magic": 60107,
               "comment": "BTC-AI-OPEN",
               "type_filling": mt5.ORDER_FILLING_IOC}
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ok": True, "msg": f"开仓成功 {action} {lot}手", "ticket": result.order}
        else:
            err = result.comment if result else "未知错误"
            return {"ok": False, "msg": f"开仓失败: {err}"}
    finally:
        mt5.shutdown()

# ============================================================
# 修改SL（移动止损用）
# ============================================================
def modify_sl(ticket: int, new_sl: float) -> bool:
    """修改持仓止损价"""
    if not mt5.initialize(path=MT5_PATH):
        return False
    try:
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
        p = positions[0]
        req = {"action": mt5.TRADE_ACTION_SLTP,
               "symbol": p.symbol,
               "position": p.ticket,
               "sl": new_sl,
               "tp": p.tp,
               "magic": 60107}
        result = mt5.order_send(req)
        return result and result.retcode == mt5.TRADE_RETCODE_DONE
    finally:
        mt5.shutdown()

# ============================================================
# 交易时间过滤
# ============================================================
def is_trade_time_allowed(params: dict) -> tuple:
    """检查当前是否在允许交易的时间段内，返回 (allowed: bool, reason: str)"""
    now = datetime.now()
    after_hour = params.get("no_trade_after_hour", 22)
    before_hour = params.get("no_trade_before_hour", 0)
    current_hour = now.hour
    if current_hour >= after_hour:
        return False, f"已过{after_hour}点，停止开仓（避免过夜费）"
    if before_hour > 0 and current_hour < before_hour:
        return False, f"未到{before_hour}点，不允许开仓"
    return True, ""

