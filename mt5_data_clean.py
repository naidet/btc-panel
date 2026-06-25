#!/usr/bin/env python3
"""
用 MT5 数据重新训练 + 重新回测
全部数据从MT5获取，不用币安
"""
import os, sys, json, pickle, time
import numpy as np
import datetime as dt

sys.path.insert(0, "D:/BTC")
os.chdir("D:/BTC")

import MetaTrader5 as mt5
from btc_trader import calc_ema, calc_rsi, calc_atr, calc_adx, calc_sma

CACHE_FILE = "mt5_data_cache_multi.pkl"

# ============================================================
# 1. MT5 DataFetcher — 完全替代Binance
# ============================================================
class MT5DataFetcher:
    """从MT5获取K线数据，替代Binance"""
    
    TF_MAP = {
        "1m": (mt5.TIMEFRAME_M1, "1m"),
        "5m": (mt5.TIMEFRAME_M5, "5m"),
        "15m": (mt5.TIMEFRAME_M15, "15m"),
        "30m": (mt5.TIMEFRAME_M30, "30m"),
        "1h": (mt5.TIMEFRAME_H1, "1h"),
        "4h": (mt5.TIMEFRAME_H4, "4h"),
        "1d": (mt5.TIMEFRAME_D1, "1d"),
    }
    
    def __init__(self, path="C:/Program Files/MetaTrader 5/terminal64.exe", symbol="BTCUSD"):
        self.path = path
        self.symbol = symbol
        self.cache = {}
        self._load_cache()
    
    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "rb") as f:
                    self.cache = pickle.load(f)
            except:
                self.cache = {}
    
    def _save_cache(self):
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(self.cache, f)
    
    def fetch_bars(self, timeframe: str = "1h", count: int = 500):
        """获取MT5 K线数据 (最旧在最前)"""
        if timeframe not in self.TF_MAP:
            return []
        
        mt5_tf, tf_name = self.TF_MAP[timeframe]
        cache_key = f"{tf_name}_{count}"
        
        # 检查缓存 (5分钟内有效)
        now = time.time()
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if now - cached.get("_time", 0) < 300:
                return cached.get("bars", [])
        
        # 从MT5获取
        try:
            mt5.initialize(path=self.path)
            mt5.symbol_select(self.symbol, True)
            
            # 估算需要获取的天数
            bar_seconds = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
            seconds = bar_seconds.get(timeframe, 3600) * count
            days = max(int(seconds / 86400) + 10, 10)
            
            start = dt.datetime.now() - dt.timedelta(days=days)
            rates = mt5.copy_rates_from(self.symbol, mt5_tf, start, 99999)
            mt5.shutdown()
            
            if rates is None or len(rates) < 30:
                print(f"  ⚠️ {timeframe}: 数据不足({len(rates) if rates else 0})")
                return []
            
            # 转为Bar对象
            bars = []
            # 取最后count根
            for r in rates[-count:]:
                bar_time = dt.datetime.fromtimestamp(r[0])
                bars.append([bar_time, r[1], r[2], r[3], r[4], r[5]])
            
            self.cache[cache_key] = {"bars": bars, "_time": now}
            self._save_cache()
            
            print(f"  ✅ MT5 {timeframe}: {len(bars)}根 ({bars[0][0].date()}~{bars[-1][0].date()})")
            return bars
        
        except Exception as e:
            print(f"  ❌ MT5 {timeframe}: {e}")
            return []
    
    def get_real_time_price(self):
        """MT5实时价格"""
        try:
            mt5.initialize(path=self.path)
            mt5.symbol_select(self.symbol, True)
            tick = mt5.symbol_info_tick(self.symbol)
            mt5.shutdown()
            return tick.bid if tick else 0
        except:
            return 0

# ============================================================
# 2. 策略信号(基于MT5数据)
# ============================================================
class RSI_EMA_MT5:
    name = "RSI+EMA 日线 (MT5)"
    
    def on_data(self, bars):
        closes = [b[4] for b in bars]  # close
        ema20 = calc_ema(closes, 20)
        rsi = calc_rsi(closes, 14)
        
        if len(closes) < 25:
            return 0
        
        price = closes[-1]
        ma = ema20[-1]
        r = rsi[-1]
        
        if price > ma and 50 < r < 70:
            return 1   # 买入
        elif price < ma and 30 < r < 50:
            return -1  # 卖出
        return 0

# ============================================================
# 3. 用MT5数据做回测
# ============================================================
def run_backtest(bars, get_signal_fn, risk=10.0, sl_atr=1.5):
    """简化回测: 每次信号变化进场, 止损=1.5xATR, 无追踪止盈"""
    closes = [b[4] for b in bars]
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    atr = calc_atr(highs, lows, closes, 14)
    
    position = 0
    entry = 0.0
    equity = 0.0
    trades = []
    peak = 0
    
    for i in range(50, len(bars)):
        price = closes[i]
        atr_v = atr[i]
        if atr_v <= 0: continue
        
        sig = get_signal_fn(bars[:i+1])
        sl_dist = atr_v * sl_atr
        
        if sig != 0 and sig != position:
            # 平旧仓
            if position != 0:
                pnl = (price - entry) if position == 1 else (entry - price)
                equity += pnl
                trades.append(pnl)
            
            # 开新仓
            position = sig
            entry = price
        
        elif sig == 0 and position != 0:
            pnl = (price - entry) if position == 1 else (entry - price)
            equity += pnl
            trades.append(pnl)
            position = 0
    
    # 平最后仓位
    if position != 0:
        pnl = (closes[-1] - entry) if position == 1 else (entry - closes[-1])
        equity += pnl
        trades.append(pnl)
    
    return {
        "pnl": equity,
        "trades": len(trades),
        "wins": sum(1 for t in trades if t > 0),
        "avg_win": np.mean([t for t in trades if t > 0]) if any(t > 0 for t in trades) else 0,
        "avg_loss": np.mean([abs(t) for t in trades if t < 0]) if any(t < 0 for t in trades) else 0,
    }

# ============================================================
# 4. 执行
# ============================================================
print("=" * 55)
print("  MT5 数据清洗 + 重新回测")
print("=" * 55)

fetcher = MT5DataFetcher()

# 获取各时间框架
bars_1d = fetcher.fetch_bars("1d", 400)
bars_4h = fetcher.fetch_bars("4h", 1000)
bars_1h = fetcher.fetch_bars("1h", 2000)

# ======== 回测 RSI+EMA (日线, MT5数据) ========
print(f"\n{'='*55}")
print("  回测: RSI+EMA 日线 (MT5数据)")
print("="*55)

s = RSI_EMA_MT5()

# 测试不同参数
for risk in [10, 25, 50, 100]:
    for sl in [1.5, 2.0, 3.0]:
        r = run_backtest(bars_1d, s.on_data, risk=risk, sl_atr=sl)
        pnl_str = f"+${r['pnl']:.2f}" if r['pnl'] >= 0 else f"-${abs(r['pnl']):.2f}"
        wr = r['wins'] / r['trades'] * 100 if r['trades'] > 0 else 0
        pf = r['avg_win'] / r['avg_loss'] if r['avg_loss'] > 0 else 99
        print(f"  Risk${risk:3d} SL{sl:.1f}x: {pnl_str:>10s}  {r['trades']:3d}笔 胜率{wr:.0f}% PF{pf:.2f} 均赢${r['avg_win']:.0f} 均亏${r['avg_loss']:.0f}")

# ======== 对比: 之前币安数据回测的RSI+EMA ========
print(f"\n{'='*55}")
print("  对比: 币安 vs MT5 数据回测效果")
print("="*55)

# 币安原版RSI+EMA
import sys
from btc_trader import DataFetcher, Backtester, RSI_EMA, get_all_strategies
binance_fetcher = DataFetcher()
binance_bars = binance_fetcher.fetch_bars("1d", 400)

if binance_bars:
    strategy = RSI_EMA()
    r_binance = Backtester.run(binance_bars, strategy, initial_capital=10000, 
                                risk_per_trade=25, trail_trigger=9999, trail_back=1, sl_atr=1.5)
    print(f"  币安数据: 净利=\${r_binance.total_pnl:.2f} ({r_binance.total_pnl_pct:+.2f}%)  {r_binance.total_trades}笔 回撤{r_binance.max_drawdown:.1f}%")

# MT5版本
mt5_result = run_backtest(bars_1d, s.on_data, risk=25, sl_atr=1.5)
pnl_str = f"+${mt5_result['pnl']:.2f}" if mt5_result['pnl'] >= 0 else f"-${abs(mt5_result['pnl']):.2f}"
print(f"  MT5数据:   净利={pnl_str}  {mt5_result['trades']}笔")

# ======== 当前信号 ========
print(f"\n{'='*55}")
print("  当前信号 (基于MT5数据)")
print("="*55)

# 日线信号
sig_1d = s.on_data(bars_1d)
print(f"  日线 RSI+EMA: {'🔴卖出' if sig_1d == -1 else '🟢买入' if sig_1d == 1 else '⚪观望'}")

# 当前价格
price = fetcher.get_real_time_price()
print(f"  MT5实时价: \${price:.2f}")

# 日线数据概览
if bars_1d:
    closes_1d = [b[4] for b in bars_1d[-5:]]
    print(f"  最近5日收盘: {[f'${c:.0f}' for c in closes_1d]}")
    
    ema20 = calc_ema([b[4] for b in bars_1d], 20)
    rsi = calc_rsi([b[4] for b in bars_1d], 14)
    print(f"  EMA20=\${ema20[-1]:.0f}  RSI={rsi[-1]:.1f}")
    print(f"  价格{'高' if closes_1d[-1] > ema20[-1] else '低'}于EMA20 → {'多头' if closes_1d[-1] > ema20[-1] else '空头'}趋势")

print(f"\n  ✅ 完成!")
