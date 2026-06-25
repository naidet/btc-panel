"""
币安吃单比模块 — Taker Buy/Sell Ratio
======================================
通过轮询币安 REST API 获取近期成交，计算主动买卖量比，
作为外部独立的市场情绪指标。

用法:
    from binance_depth import start_collector, get_binance_bias, stop_collector
    
    start_collector()          # 启动后台采集线程
    bias = get_binance_bias()  # 返回 {"bias": -1~1, "taker_buy_ratio": 0.5, "trades": 100}
    stop_collector()           # 停止

删除此文件 = 移除币安数据源，面板正常运行不受影响
"""

import threading
import time
import json
from collections import deque
from datetime import datetime, timedelta

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ============================================================
# 配置
# ============================================================
SYMBOL = "BTCUSDT"
INTERVAL = 10          # 轮询间隔(秒)
HISTORY_WINDOW = 60    # 保留最近N秒的数据
API_BASE = "https://api.binance.com"

# ============================================================
# 内部状态
# ============================================================
_buffer = deque(maxlen=600)   # [(timestamp, buy_vol, sell_vol)]
_running = False
_collector_thread = None
_lock = threading.Lock()
_last_error = None
_last_update = None


def _fetch_recent_trades(limit: int = 500) -> list:
    """从币安拉取近期成交"""
    url = f"{API_BASE}/api/v3/aggTrades"
    params = {"symbol": SYMBOL, "limit": limit}
    
    resp = requests.get(url, params=params, timeout=8)
    resp.raise_for_status()
    return resp.json()


def _classify_trades(trades: list, mid_price: float = None):
    """
    分类每笔成交为主动买/卖
    方法: 价格变化方向判断
      - 当前成交价 > 上一笔价 → 主动买入
      - 当前成交价 < 上一笔价 → 主动卖出
      - 价格不变 → 沿用上一笔方向
    返回: (buy_volume, sell_volume, trade_count)
    """
    buy_vol = 0.0
    sell_vol = 0.0
    last_dir = 0  # 1=buy, -1=sell
    
    for i in range(1, len(trades)):
        t = trades[i]
        prev = trades[i - 1]
        price = float(t["p"])
        qty = float(t["q"])
        prev_price = float(prev["p"])
        
        if price > prev_price:
            buy_vol += qty
            last_dir = 1
        elif price < prev_price:
            sell_vol += qty
            last_dir = -1
        else:
            if last_dir > 0:
                buy_vol += qty
            elif last_dir < 0:
                sell_vol += qty
            else:
                # 第一笔无法判断，对半
                buy_vol += qty * 0.5
                sell_vol += qty * 0.5
    
    return buy_vol, sell_vol, len(trades)


def _get_mid_price() -> float:
    """获取当前中间价"""
    try:
        url = f"{API_BASE}/api/v3/ticker/bookTicker"
        resp = requests.get(url, params={"symbol": SYMBOL}, timeout=5)
        data = resp.json()
        bid = float(data["bidPrice"])
        ask = float(data["askPrice"])
        return (bid + ask) / 2
    except:
        return 0


def _collect_loop():
    """后台采集循环"""
    global _last_error, _last_update
    
    while _running:
        try:
            # 拉取近期成交
            trades = _fetch_recent_trades(500)
            
            if len(trades) < 10:
                _last_error = f"成交数据太少({len(trades)}笔)"
                time.sleep(INTERVAL)
                continue
            
            # 分类
            buy_vol, sell_vol, n = _classify_trades(trades)
            now = time.time()
            
            with _lock:
                _buffer.append((now, buy_vol, sell_vol))
                _last_error = None
                _last_update = datetime.now()
            
        except Exception as e:
            _last_error = str(e)
        
        time.sleep(INTERVAL)


def start_collector():
    """启动后台采集"""
    global _running, _collector_thread
    
    if not HAS_REQUESTS:
        print("[binance] requests 模块未安装, 跳过")
        return False
    
    if _running:
        return True
    
    _running = True
    _collector_thread = threading.Thread(target=_collect_loop, daemon=True)
    _collector_thread.start()
    
    # 等第一笔数据
    for _ in range(15):
        if _last_update:
            return True
        time.sleep(1)
    
    return bool(_last_update)


def stop_collector():
    """停止后台采集"""
    global _running
    _running = False


def get_binance_bias() -> dict:
    """
    获取当前币安吃单偏向
    
    返回:
      {"ready": True/False,
       "taker_buy_ratio": 0.0~1.0,   # 主动买入占比
       "bias": -1.0~1.0,             # 偏向: 正=偏多, 负=偏空, 0=中性
       "total_volume": float,         # 窗口内总成交量
       "trades": int,                 # 成交笔数
       "error": str}                  # 错误信息
    """
    if not HAS_REQUESTS:
        return {"ready": False, "error": "requests 未安装"}
    
    if _last_error:
        return {"ready": False, "error": _last_error}
    
    with _lock:
        if len(_buffer) < 2:
            return {"ready": False, "error": "数据采集中, 请稍候"}
        
        # 取最近60秒的数据
        now = time.time()
        recent = [(t, b, s) for t, b, s in _buffer if now - t < HISTORY_WINDOW]
        
        if not recent:
            return {"ready": False, "error": "无近期数据"}
        
        total_buy = sum(b for _, b, _ in recent)
        total_sell = sum(s for _, _, s in recent)
        total = total_buy + total_sell
        
        if total <= 0:
            return {"ready": False, "error": "成交量为0"}
        
        ratio = total_buy / total
        
        # bias: 0.5=中性 → 0, 0.7=偏多 → 0.4, 0.3=偏空 → -0.4
        bias = (ratio - 0.5) * 2  # 映射到 -1 ~ 1
        
    return {
        "ready": True,
        "taker_buy_ratio": round(ratio, 4),
        "bias": round(bias, 4),
        "total_volume": round(total, 2),
        "trades": len(recent),
    }


def get_status() -> dict:
    """获取模块运行状态"""
    return {
        "running": _running,
        "has_requests": HAS_REQUESTS,
        "last_update": _last_update.strftime("%H:%M:%S") if _last_update else None,
        "last_error": _last_error,
        "buffer_size": len(_buffer),
    }


# ============================================================
# 面板集成用: 开仓前确认
# ============================================================
def confirm_trade(direction: str, min_bias: float = 0.15) -> tuple:
    """
    开仓前用币安吃单比做最后确认
    
    direction: "BUY" / "SELL"
    min_bias: 最小偏向阈值 (默认0.15, 即ratio>0.575或<0.425)
    
    返回: (通过, 原因)
    """
    bias_data = get_binance_bias()
    
    if not bias_data.get("ready"):
        return True, f"币安:{bias_data.get('error','未就绪')}→放行"
    
    bias = bias_data["bias"]
    ratio = bias_data["taker_buy_ratio"]
    
    if direction == "BUY":
        if bias > min_bias:
            return True, f"币安:偏多(ratio={ratio:.2f})→确认"
        elif bias < -min_bias:
            return False, f"币安:偏空(ratio={ratio:.2f})→拦截"
        else:
            return True, f"币安:中性(ratio={ratio:.2f})→放行"
    else:  # SELL
        if bias < -min_bias:
            return True, f"币安:偏空(ratio={ratio:.2f})→确认"
        elif bias > min_bias:
            return False, f"币安:偏多(ratio={ratio:.2f})→拦截"
        else:
            return True, f"币安:中性(ratio={ratio:.2f})→放行"


if __name__ == "__main__":
    print("启动币安数据采集...")
    ok = start_collector()
    print(f"启动: {'成功' if ok else '失败'}")
    print(f"状态: {get_status()}")
    
    for i in range(3):
        time.sleep(5)
        bias = get_binance_bias()
        print(f"  [{i+1}] bias={bias}")
    
    print("\n模拟开仓确认:")
    r, msg = confirm_trade("SELL")
    print(f"  SELL: {r} → {msg}")
    r, msg = confirm_trade("BUY")
    print(f"  BUY: {r} → {msg}")
    
    stop_collector()
    print("已停止")
