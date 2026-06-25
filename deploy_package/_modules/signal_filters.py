"""
BTC 策略过滤器 — 独立模块，可随时删除不影响面板运行
=====================================================
策略①: EMA50 趋势方向过滤 — 只做趋势方向的交易
策略②: 日线结构对齐 — 日线定方向，小周期找入场

用法:
    from signal_filters import apply_filters
    filtered = apply_filters(resonance_data)
    # resonance_data: list of {"name": tf, "signal": -1/0/1, "price", "ema20", "rsi", ...}
    # 返回: 被置零的 resonance_data + filter_reasons

删除此文件 = 移除所有过滤器，面板自动回退到纯共振策略
"""

import MetaTrader5 as mt5
from btc_trader import calc_ema

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

# ============================================================
# 策略①: EMA 趋势方向过滤
# ============================================================
def filter_ema_trend(resonance_data: list, ema_period: int = 50) -> dict:
    """
    检查各周期的 EMA50 斜率，过滤逆势信号
    
    返回: {"reasons": [...], "blocked_signals": ["1h", "4h", ...]}
    
    逻辑:
      - EMA50 slope > 0 → 只允许多头 (signal=1), 空头信号置零
      - EMA50 slope < 0 → 只允许空头 (signal=-1), 多头信号置零
      - EMA50 平 → 不限制 (震荡期, 允许两边)
    """
    reasons = []
    blocked = []
    
    try:
        # 取额外数据算 EMA50
        mt5.initialize(path=MT5_PATH)
        mt5.symbol_select("BTCUSD", True)
        
        tf_map = {
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
        }
        
        for tf_name, m5tf in tf_map.items():
            rates = mt5.copy_rates_from_pos("BTCUSD", m5tf, 0, ema_period + 10)
            if rates is None or len(rates) < ema_period:
                reasons.append(f"EMA50.{tf_name}: 数据不足")
                continue
            
            closes = [r[4] for r in rates]
            ema_arr = calc_ema(closes, ema_period)
            if len(ema_arr) < 3:
                continue
            
            # 算斜率: 最近3根 EMA50 的线性回归斜率
            recent = ema_arr[-5:]  # 取最近5根
            if len(recent) < 3:
                continue
            n = len(recent)
            x_mean = (n - 1) / 2
            y_mean = sum(recent) / n
            slope = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
            slope /= sum((i - x_mean) ** 2 for i in range(n))
            slope = slope / abs(recent[-1]) * 100 if recent[-1] else 0  # 百分比斜率
            
            # 找对应周期的信号
            for item in resonance_data:
                if item["name"] != tf_name:
                    continue
                sig = item["signal"]
                
                if slope > 0.01 and sig == -1:
                    # EMA抬头但信号看空 → 过滤掉
                    item["signal"] = 0
                    item["_filtered_by"] = "ema_trend"
                    blocked.append(tf_name)
                    reasons.append(f"EMA50.{tf_name} ↑ 过滤空信号")
                elif slope < -0.01 and sig == 1:
                    # EMA低头但信号看多 → 过滤掉
                    item["signal"] = 0
                    item["_filtered_by"] = "ema_trend"
                    blocked.append(tf_name)
                    reasons.append(f"EMA50.{tf_name} ↓ 过滤多信号")
        
        mt5.shutdown()
    except Exception as e:
        reasons.append(f"EMA趋势过滤异常: {e}")
        try: mt5.shutdown()
        except: pass
    
    return {"reasons": reasons, "blocked_signals": blocked, "name": "EMA趋势"}


# ============================================================
# 策略②: 日线结构对齐
# ============================================================
def filter_daily_structure(resonance_data: list, fast_ema: int = 20, slow_ema: int = 50) -> dict:
    """
    日线 EMA20 vs EMA50 定大方向，过滤小周期逆向信号
    
    返回: {"reasons": [...], "blocked_signals": [...], "daily_bias": "bull"/"bear"/"neutral"}
    
    逻辑:
      - 日线 EMA20 > EMA50 + 定多 → 1h/4h 空头信号全过滤
      - 日线 EMA20 < EMA50 + 定空 → 1h/4h 多头信号全过滤
      - 日线 EMA20 ≈ EMA50 (差<1%) → 维持日线信号, 不额外过滤
    """
    reasons = []
    blocked = []
    bias = "neutral"
    
    # 从 resonance_data 找到日线数据
    daily_item = None
    for item in resonance_data:
        if item["name"] == "1d":
            daily_item = item
            break
    
    if not daily_item or daily_item["bars"] < slow_ema:
        reasons.append("日线结构: 数据不足")
        return {"reasons": reasons, "blocked_signals": blocked, "daily_bias": bias, "name": "日线结构"}
    
    try:
        # 单独拉日线数据算 EMA20 和 EMA50
        mt5.initialize(path=MT5_PATH)
        mt5.symbol_select("BTCUSD", True)
        rates = mt5.copy_rates_from_pos("BTCUSD", mt5.TIMEFRAME_D1, 0, slow_ema + 10)
        mt5.shutdown()
        
        if rates is None or len(rates) < slow_ema:
            reasons.append("日线结构: MT5数据不足")
            return {"reasons": reasons, "blocked_signals": blocked, "daily_bias": bias, "name": "日线结构"}
        
        closes = [r[4] for r in rates]
        ema20_arr = calc_ema(closes, fast_ema)
        ema50_arr = calc_ema(closes, slow_ema)
        
        e20 = ema20_arr[-1]
        e50 = ema50_arr[-1]
        diff_pct = abs(e20 - e50) / e50 * 100 if e50 > 0 else 0
        
        if e20 > e50 and diff_pct > 1.0:
            bias = "bull"
            reasons.append(f"日线EMA20>{fast_ema} EMA50>{slow_ema} 定多 (+{diff_pct:.1f}%)")
            # 过滤 1h/4h 空头
            for item in resonance_data:
                if item["name"] in ("1h", "4h") and item["signal"] == -1:
                    item["signal"] = 0
                    item["_filtered_by"] = "daily_structure"
                    blocked.append(item["name"])
            reasons.append(f"    → 过滤 {len(blocked)} 个空头信号")
        elif e20 < e50 and diff_pct > 1.0:
            bias = "bear"
            reasons.append(f"日线EMA20<{fast_ema} EMA50<{slow_ema} 定空 (-{diff_pct:.1f}%)")
            # 过滤 1h/4h 多头
            for item in resonance_data:
                if item["name"] in ("1h", "4h") and item["signal"] == 1:
                    item["signal"] = 0
                    item["_filtered_by"] = "daily_structure"
                    blocked.append(item["name"])
            reasons.append(f"    → 过滤 {len(blocked)} 个多头信号")
        else:
            bias = "neutral"
            reasons.append(f"日线EMA{fast_ema}≈EMA{slow_ema} 震荡({diff_pct:.1f}%) → 不限制")
    
    except Exception as e:
        reasons.append(f"日线结构异常: {e}")
        try: mt5.shutdown()
        except: pass
    
    return {"reasons": reasons, "blocked_signals": blocked, "daily_bias": bias, "name": "日线结构"}


# ============================================================
# 组合应用
# ============================================================
def apply_filters(resonance_data: list) -> dict:
    """
    依次应用所有过滤器, 返回过滤结果摘要
    面板调用此函数即可, 不需要单独调子函数
    
    返回:
      {"filtered": bool, "filter_results": [...], "total_blocked": int}
    """
    filter_results = []
    total_blocked = 0
    
    # 先复制一份原始信号 (用于对比)
    original = {item["name"]: item["signal"] for item in resonance_data}
    
    # 策略①: EMA趋势方向
    r1 = filter_ema_trend(resonance_data)
    filter_results.append(r1)
    total_blocked += len(r1.get("blocked_signals", []))
    
    # 策略②: 日线结构 (在①之后, 避免重复过滤同一信号)
    r2 = filter_daily_structure(resonance_data)
    filter_results.append(r2)
    total_blocked += len(r2.get("blocked_signals", []))
    
    # 对比变化
    for item in resonance_data:
        name = item["name"]
        if name in original and original[name] != 0 and item["signal"] == 0:
            item["_filtered"] = True
    
    return {
        "filtered": total_blocked > 0,
        "filter_results": filter_results,
        "total_blocked": total_blocked,
        "original": original,
    }


if __name__ == "__main__":
    # 测试
    sample = [
        {"name": "1h", "signal": -1, "rsi": 45, "ema20": 64200, "price": 64100, "adx": 30, "macd_hist": -50, "bars": 50},
        {"name": "4h", "signal": -1, "rsi": 48, "ema20": 64150, "price": 64100, "adx": 28, "macd_hist": -80, "bars": 50},
        {"name": "1d", "signal": -1, "rsi": 40, "ema20": 65200, "price": 64100, "adx": 22, "macd_hist": -200, "bars": 50},
    ]
    result = apply_filters(sample)
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
