"""
BTC AI Trading System - Core Trading Module (Fixed)
Provides: MT5 interface, signal calculation, risk management, trade execution
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
    "sl_min": 800,           # 最小止损距离(点数)
    "tp_atr_mult": 2.0,
    "tp_min": 1500,          # 最小止盈距离(点数)
    "trail_profit": 3,
    "trail_dist": 200,        # 移动止损距离(点数)
    "profit_lock_trigger": 5,  # 盈利锁定触发$(金额)
    "profit_lock_pullback": 20, # 盈利回撤平仓%(百分比)
    "risk_per_trade": 20,     # 每笔风险$
    "lot_fixed": 0,            # 固定手数(>0时使用)
    "lot_min": 0.01,
    "max_daily_loss": 300,
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
# 当日盈亏追踪 (线程安全, 不依赖MT5连接)
# ============================================================
_daily_pnl_state = {"date": None, "start_balance": None, "pnl": 0.0}

def get_daily_pnl() -> dict:
    """追踪当日盈亏, 使用MT5账户信息, 带锁保护"""
    global _daily_pnl_state
    today = datetime.now().strftime("%Y%m%d")
    s = _daily_pnl_state
    
    # 尝试从MT5读取余额 (带锁, 避免冲突)
    balance = None
    if _mt5_lock.acquire(timeout=3):
        try:
            if mt5.initialize(path=MT5_PATH):
                acct = mt5.account_info()
                if acct:
                    balance = acct.balance
                mt5.shutdown()
        except:
            try: mt5.shutdown()
            except: pass
        finally:
            try: _mt5_lock.release()
            except: pass
    
    if balance is not None:
        if s["date"] != today or s["start_balance"] is None:
            s["date"] = today
            s["start_balance"] = balance
            s["pnl"] = 0.0
        else:
            s["pnl"] = balance - s["start_balance"]
        return {"date": s["date"], "start_balance": s["start_balance"], 
                "pnl": s["pnl"], "balance": balance}
    else:
        # MT5不可用, 返回缓存值
        return {"date": today, "start_balance": s.get("start_balance"), 
                "pnl": s.get("pnl", 0.0)}

# ============================================================
# MT5 数据获取 (带锁)
# ============================================================
def fetch_all_mt5_data(symbol: str, include_h1: bool = True) -> Optional[dict]:
    """获取多时间框架K线数据, 返回各周期Bar列表 (带锁)"""
    if not _mt5_lock.acquire(timeout=10):
        return None
    try:
        if not mt5.initialize(path=MT5_PATH):
            return None
        mt5.symbol_select(symbol, True)
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
    except:
        return None
    finally:
        try: mt5.shutdown()
        except: pass
        try: _mt5_lock.release()
        except: pass

def get_mt5_account_info() -> Optional[dict]:
    """获取账户信息 (带锁)"""
    if not _mt5_lock.acquire(timeout=5):
        return None
    try:
        if not mt5.initialize(path=MT5_PATH):
            return None
        acct = mt5.account_info()
        if acct:
            return {"balance": acct.balance, "equity": acct.equity,
                    "margin": acct.margin, "free_margin": acct.margin_free,
                    "login": acct.login, "server": acct.server}
        return None
    finally:
        try: mt5.shutdown()
        except: pass
        try: _mt5_lock.release()
        except: pass

def get_mt5_positions(symbol: str = "") -> list:
    """获取当前持仓 (带锁)"""
    if not _mt5_lock.acquire(timeout=5):
        return []
    try:
        if not mt5.initialize(path=MT5_PATH):
            return []
        mt5.symbol_select(symbol, True) if symbol else None
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return list(positions or [])
    finally:
        try: mt5.shutdown()
        except: pass
        try: _mt5_lock.release()
        except: pass

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
# HMM 市场状态判断 (简化版)
# ============================================================
_hmm_state = {"state": -1, "confidence": 0.0, "expected_duration": 0}

def update_hmm_state(symbol: str):
    """更新HMM市场状态"""
    global _hmm_state
    data = fetch_all_mt5_data(symbol, include_h1=False)
    if not data or "H4" not in data:
        return
    bars = data["H4"]
    closes = np.array([b.close for b in bars[-50:]])
    returns = np.diff(closes) / closes[:-1]
    vol = np.std(returns) * np.sqrt(6 * 24)
    sma20 = np.mean(closes[-20:])
    sma50 = np.mean(closes[-50:])
    trend = 1 if sma20 > sma50 else -1
    # 计算历史波动率百分位
    hist_vols = []
    for i in range(50, len(closes)):
        h = np.std(np.diff(closes[:i]) / closes[:i-1]) if i > 30 else 0
        hist_vols.append(h)
    vol_threshold = np.percentile(hist_vols, 80) if hist_vols else vol
    if vol > vol_threshold:
        if trend == -1:
            _hmm_state = {"state": 2, "confidence": 0.9, "expected_duration": 8}
        else:
            _hmm_state = {"state": 0, "confidence": 0.7, "expected_duration": 12}
    else:
        _hmm_state = {"state": 1, "confidence": 0.6, "expected_duration": 20}

def get_hmm_state() -> dict:
    return dict(_hmm_state)

# ============================================================
# 风险控制检查
# ============================================================
def check_risk_gates(symbol: str, side: str, params: dict) -> Tuple[bool, str]:
    """检查风控闸门, 返回 (passed, reason)"""
    # 日亏检查
    daily = get_daily_pnl()
    if daily.get("pnl", 0) <= -params.get("max_daily_loss", 300):
        return False, f"日亏${abs(daily['pnl']):.0f}超限"
    
    # 使用锁访问MT5
    if not _mt5_lock.acquire(timeout=10):
        return False, "MT5忙, 跳过"
    try:
        if not mt5.initialize(path=MT5_PATH):
            return True, ""  # MT5不可用, 允许交易 (主循环会处理)
        mt5.symbol_select(symbol, True)
        
        # 点差检查
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
            atr_avg = np.mean(trs) if len(trs) >= 30 else atr
            if atr > atr_avg * params.get("atr_spike_mult", 2.0):
                return False, f"ATR飙升{atr/atr_avg:.1f}x"
    finally:
        try: mt5.shutdown()
        except: pass
        try: _mt5_lock.release()
        except: pass
    
    # HMM过滤 (不需要MT5连接)
    hmm = get_hmm_state()
    if hmm["state"] == 2 and side == "BUY":
        return False, "HMM高波回撤, 不做多"
    if hmm["state"] == 0 and side == "SELL":
        return False, "HMM强势趋势, 不做空"
    return True, ""

# ============================================================
# 交易执行 (核心函数, 已修复)
# ============================================================
def execute_trade(action: str, symbol: str, params: dict = None) -> dict:
    """
    执行交易指令
    action: "BUY", "SELL", "CLOSE"
    symbol: 交易品种
    params: 参数字典 (不传则自动加载)
    """
    if params is None:
        params = load_params()
    
    # 加载品种专属参数
    sym_params, _ = _load_symbol_params(symbol)
    
    if not _mt5_lock.acquire(timeout=15):
        return {"ok": False, "msg": "MT5忙, 请稍后重试"}
    try:
        if not mt5.initialize(path=MT5_PATH):
            return {"ok": False, "msg": "MT5连接失败"}
        mt5.symbol_select(symbol, True)
        
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if not tick or not info:
            return {"ok": False, "msg": "无法获取报价或品种信息"}
        
        # ============================================================
        # 平仓
        # ============================================================
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
        
        # ============================================================
        # 开仓 (BUY/SELL)
        # ============================================================
        is_buy = (action == "BUY")
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        
        # 获取最新价格 (避免过期)
        price = tick.ask if is_buy else tick.bid
        
        # --- 计算SL/TP距离 (点数) ---
        sl_min_points = int(params.get("sl_min", 800) or sym_params.get("sl_min", 800))
        tp_min_points = int(params.get("tp_min", 1500) or sym_params.get("tp_min", 1500))
        sl_atr_mult = float(params.get("sl_atr_mult", 1.5) or sym_params.get("sl_atr_mult", 1.5))
        tp_atr_mult = float(params.get("tp_atr_mult", 2.0) or sym_params.get("tp_atr_mult", 2.0))
        
        # 从H4计算ATR (点数)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 20)
        sl_points = sl_min_points
        tp_points = tp_min_points
        if rates is not None and len(rates) > 14:
            trs = []
            for i in range(1, len(rates)):
                h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                trs.append(max(h-l, abs(h-c), abs(l-c)))
            atr_price = np.mean(trs[-14:])  # ATR (价格单位)
            atr_points = atr_price / info.point  # 转换为点数
            sl_points = max(sl_min_points, int(atr_points * sl_atr_mult))
            tp_points = max(tp_min_points, int(atr_points * tp_atr_mult))
        
        # --- 计算SL/TP价格 ---
        point = info.point
        sl_price = (price - sl_points * point) if is_buy else (price + sl_points * point)
        tp_price = (price + tp_points * point) if is_buy else (price - tp_points * point)
        
        # --- 计算手数 ---
        lot_fixed = float(params.get("lot_fixed", 0) or sym_params.get("lot_fixed", 0))
        lot_min = max(float(params.get("lot_min", 0.01) or sym_params.get("lot_min", 0.01)), 
                     info.volume_min or 0.01)
        
        if lot_fixed > 0:
            lot = lot_fixed
        else:
            # 按风险计算手数
            risk = float(params.get("risk_per_trade", 20) or sym_params.get("risk_per_trade", 20))
            # 每点价值 (美元/点/手)
            # BTC: 1手=1BTC, 1点=point, 价值=1*point*price
            point_value = info.trade_contract_size * point * price / info.leverage if info.leverage > 0 else info.trade_contract_size * point
            risk_per_point = point_value  # 1手时, 1点的价值
            if risk_per_point > 0:
                lot = risk / (sl_points * risk_per_point)
            else:
                lot = lot_min
            lot = max(lot_min, round(lot, 2))
        
        lot = max(lot_min, min(lot, info.volume_max or 100))
        
        # --- 发送开仓订单 ---
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
            return {"ok": True, "msg": f"开仓成功 {action} {lot}手 SL:{sl_price:.5f} TP:{tp_price:.5f}", 
                    "ticket": result.order, "sl": sl_price, "tp": tp_price}
        else:
            err = result.comment if result else "未知错误"
            return {"ok": False, "msg": f"开仓失败: {err}"}
    finally:
        try: mt5.shutdown()
        except: pass
        try: _mt5_lock.release()
        except: pass

# ============================================================
# 修改SL (移动止损用, 已修复)
# ============================================================
def modify_sl(ticket: int, new_sl: float) -> bool:
    """修改持仓止损价"""
    if not _mt5_lock.acquire(timeout=5):
        return False
    try:
        if not mt5.initialize(path=MT5_PATH):
            return False
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
        return result and result.retcode == mt5.TRADE_RETCODE_DONE
    finally:
        try: mt5.shutdown()
        except: pass
        try: _mt5_lock.release()
        except: pass

# ============================================================
# 交易时间过滤
# ============================================================
def is_trade_time_allowed(params: dict) -> Tuple[bool, str]:
    """检查当前是否在允许交易的时间段内"""
    now = datetime.now()
    after_hour = int(params.get("no_trade_after_hour", 22))
    before_hour = int(params.get("no_trade_before_hour", 0))
    current_hour = now.hour
    if current_hour >= after_hour:
        return False, f"已过{after_hour}点, 停止开仓(避免过夜费)"
    if before_hour > 0 and current_hour < before_hour:
        return False, f"未到{before_hour}点, 不允许开仓"
    return True, ""
