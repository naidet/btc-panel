#!/usr/bin/env python3
"""MT5 K线预测模型 — 优化版 (快速)"""
import os, sys, json, pickle, time
import numpy as np
import datetime as dt

sys.path.insert(0, "D:/BTC")
os.chdir("D:/BTC")

import MetaTrader5 as mt5
from btc_trader import *

CACHE_FILE = "mt5_data_cache.pkl"
MODEL_FILE = "kline_model.pkl"

# ============================================================
# 1. 从MT5获取数据 (带缓存)
# ============================================================
def get_mt5_bars(tf, days, name):
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            cache = pickle.load(f)
        if name in cache:
            bars = cache[name]
            if len(bars) > 50:
                print(f"  {name}: {len(bars)}根 (缓存)")
                return bars
    
    print(f"  {name}: 从MT5获取...", end="", flush=True)
    mt5.initialize(path="C:/Program Files/MetaTrader 5/terminal64.exe")
    mt5.symbol_select("BTCUSD", True)
    start = dt.datetime.now() - dt.timedelta(days=days)
    rates = mt5.copy_rates_from("BTCUSD", tf, start, 99999)
    mt5.shutdown()
    
    if rates is None or len(rates) < 50:
        print(f" 数据不足({len(rates) if rates else '?'})")
        return []
    
    bars = []
    for r in rates:
        bars.append([dt.datetime.fromtimestamp(r[0]), r[1], r[2], r[3], r[4]])
    print(f" {len(bars)}根")
    return bars

# 缓存管理
cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "rb") as f:
            cache = pickle.load(f)
    except:
        cache = {}

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

print("=" * 50)
print("  MT5 K线预测模型")
print("=" * 50)

# 获取数据
for name, tf, days in [
    ("5m", mt5.TIMEFRAME_M5, 35),
    ("15m", mt5.TIMEFRAME_M15, 95),
    ("30m", mt5.TIMEFRAME_M30, 185),
    ("1h", mt5.TIMEFRAME_H1, 370),
]:
    bars = get_mt5_bars(tf, days, name)
    if bars:
        cache[name] = bars

if not cache:
    # 至少获取1h
    print("\n  尝试仅获取1h数据...")
    bars_1h = get_mt5_bars(mt5.TIMEFRAME_H1, 370, "1h")
    if bars_1h:
        cache["1h"] = bars_1h

# 保存缓存
print("  保存缓存...")
with open(CACHE_FILE, "wb") as f:
    pickle.dump(cache, f)

if not cache or sum(len(v) for v in cache.values()) < 100:
    print("  ❌ 数据严重不足，退出")
    sys.exit(1)

# ============================================================
# 2. 对齐 + 特征提取
# ============================================================
print("\n  构建特征...")

def get_bars_at_time(bars, target_time):
    """找到最接近target_time的K线索引"""
    best = None
    for j in range(len(bars)):
        t = bars[j][0]
        if t <= target_time:
            best = j
        else:
            break
    return best

# 用1h作为目标
target_bars = cache.get("1h", list(cache.values())[0])
print(f"  目标: 1h ({len(target_bars)}根)")

X, Y, feat_names = [], [], None

# 窗口滑动
window = 24  # 用过去24根1h K线
for i in range(window + 2, len(target_bars) - 1):
    target_bar = target_bars[i]
    t = target_bar[0]
    
    # 单时间框架特征(简化版)
    segment = target_bars[i-window:i]
    closes = [b[4] for b in segment]
    highs = [b[2] for b in segment]
    lows = [b[3] for b in segment]
    price = closes[-1]
    
    if price <= 0: continue
    
    # 简单特征
    feats = []
    # 趋势: 过去N根K线的涨跌
    feats.append(1 if closes[-1] > closes[-2] else 0)         # 上根涨跌
    feats.append(1 if closes[-1] > closes[-window] else 0)     # 长期趋势
    feats.append((price - min(closes)) / (max(closes) - min(closes) + 0.01))  # 相对位置
    feats.append((highs[-1] - lows[-1]) / price)                # 振幅
    feats.append(np.std(closes[-6:]) / price)                   # 短期波动率
    feats.append(np.std(closes) / price)                        # 长期波动率
    
    # 目标
    next_close = target_bars[i+1][4]
    target = 1 if next_close > closes[-1] else 0
    
    if feat_names is None:
        feat_names = [f"f{j}" for j in range(len(feats))]
    
    X.append(feats)
    Y.append(target)

X = np.array(X)
Y = np.array(Y)
print(f"  样本: {len(X)} | 正样本: {sum(Y)/len(Y)*100:.1f}%")

# ============================================================
# 3. 训练
# ============================================================
print("\n  训练 RandomForest...")

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
Y_train, Y_test = Y[:split], Y[split:]

model = RandomForestClassifier(
    n_estimators=100, max_depth=6, min_samples_leaf=20, random_state=42
)
model.fit(X_train, Y_train)

train_acc = model.score(X_train, Y_train)
test_acc = model.score(X_test, Y_test)
preds = model.predict(X_test)

buy_total = sum(preds == 1)
buy_win = sum(1 for i in range(len(preds)) if preds[i] == 1 and Y_test[i] == 1)
sell_total = sum(preds == 0)
sell_win = sum(1 for i in range(len(preds)) if preds[i] == 0 and Y_test[i] == 0)

baseline = max(sum(Y_test) / len(Y_test), 1 - sum(Y_test) / len(Y_test))

print(f"  训练准确率: {train_acc*100:.1f}%")
print(f"  验证准确率: {test_acc*100:.1f}% (基准{baseline*100:.1f}%)")
if buy_total > 0:
    print(f"  买入胜率: {buy_win/buy_total*100:.1f}% ({buy_win}/{buy_total})")
if sell_total > 0:
    print(f"  卖出胜率: {sell_win/sell_total*100:.1f}% ({sell_win}/{sell_total})")

# ============================================================
# 4. 保存模型
# ============================================================
model_data = {
    "model": model,
    "feature_names": feat_names,
    "target_tf": "1h",
    "train_acc": train_acc,
    "test_acc": test_acc,
    "trained_at": dt.datetime.now().isoformat(),
    "samples": len(X),
    "mt5_only": True,
}

with open(MODEL_FILE, "wb") as f:
    pickle.dump(model_data, f)

print(f"\n  ✅ 模型已保存: {MODEL_FILE}")
print(f"  大小: {os.path.getsize(MODEL_FILE)/1024:.0f}KB")

# ============================================================
# 5. 对比: RSI+EMA 基准
# ============================================================
print(f"\n  对比基准(RSI+EMA):")
s = RSI_EMA()
bars_for_sig = []
for b in target_bars:
    bars_for_sig.append(Bar(time=b[0], open=b[1], high=b[2], low=b[3], close=b[4], volume=0))

sig = s.on_data(bars_for_sig)
prevsig = 0
rsi_pnl = 0
for i in range(window, len(target_bars) - 1):
    sig = s.on_data(bars_for_sig[:i+1])
    if sig.signal != 0 and sig.signal != prevsig:
        entry = target_bars[i][4]
        prevsig = sig.signal
    elif sig.signal == 0 and prevsig != 0:
        exit_p = target_bars[i][4]
        rsi_pnl += (exit_p - entry) if prevsig == 1 else (entry - exit_p)
        prevsig = 0
# 最后平仓
if prevsig != 0:
    exit_p = target_bars[-1][4]
    rsi_pnl += (exit_p - entry) if prevsig == 1 else (entry - exit_p)

print(f"  RSI+EMA策略盈亏: \${rsi_pnl:.2f}")
print(f"\n  训练完成!")
