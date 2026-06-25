#!/usr/bin/env python3
"""
BTC Trading Bot — 回测 + 实时行情监控
======================================
功能:
  1. 历史回测 (1m/5m/15m/1h/4h/1d 任意周期)
  2. 实时行情监控 (每分钟自动刷新)
  3. 多个策略可选
  4. 自动生成盈亏曲线图

用法:
  pip install pandas matplotlib ccxt numpy
  python btc_trader.py

作者: Senior Developer @ AI Trading System
"""

import os, sys, time, json, datetime, warnings
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
# pandas + matplotlib 改为按需加载 (import 2-3秒, 面板不需要)
# import pandas as pd
# import matplotlib.pyplot as plt
# import matplotlib.dates as mdates

warnings.filterwarnings("ignore")

# ======================================================================
#  1. 数据结构
# ======================================================================

@dataclass
class Bar:
    """一根K线"""
    time: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Trade:
    """一笔交易"""
    entry_time: datetime.datetime
    exit_time: Optional[datetime.datetime] = None
    side: str = ""       # "BUY" or "SELL"
    entry_price: float = 0.0
    exit_price: float = 0.0
    size: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""

@dataclass
class EquityPoint:
    time: datetime.datetime
    equity: float
    drawdown: float

@dataclass
class BacktestResult:
    """回测结果"""
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    total_trades: int = 0
    win_trades: int = 0
    lose_trades: int = 0
    sharpe: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0


# ======================================================================
#  2. 数据获取器 (Binance 免费API)
# ======================================================================

class DataFetcher:
    """
    从Binance获取历史/实时K线数据
    无需API Key（仅限公开数据）
    """
    
    BINANCE_URL = "https://api.binance.com/api/v3"
    TIMEFRAMES = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h",
        "12h": "12h", "1d": "1d", "1w": "1w"
    }
    
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self._cache = {}
    
    def _fetch_kline(self, interval: str, limit: int = 100,
                     start_time: Optional[int] = None,
                     end_time: Optional[int] = None) -> list:
        """调用 Binance API 获取K线数据"""
        import urllib.request
        import urllib.parse
        
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }
        if start_time: params["startTime"] = start_time
        if end_time:   params["endTime"] = end_time
        
        url = f"{self.BINANCE_URL}/klines?{urllib.parse.urlencode(params)}"
        
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"  ⚠️ 请求失败: {e}")
            return []
    
    def fetch_bars(self, timeframe: str = "1h", count: int = 500) -> list[Bar]:
        """
        获取历史K线 (按时间正序: 旧→新)
        
        参数:
            timeframe: 1m/5m/15m/1h/4h/1d
            count: 需要多少根K线
        返回:
            Bar 列表 (最旧的在最前)
        """
        tf = self.TIMEFRAMES.get(timeframe, "1h")
        
        all_bars = []
        remaining = count
        while remaining > 0:
            take = min(remaining, 1000)
            if all_bars:
                # 向上翻页: 获取比已有最旧K线更早的数据
                oldest = all_bars[0]  # all_bars[0] = 最旧的
                prev_end = int(oldest.time.timestamp() * 1000 - 1)
                raw = self._fetch_kline(tf, limit=take, end_time=prev_end)
            else:
                raw = self._fetch_kline(tf, limit=take)
            
            if not raw:
                break
            
            batch = []
            for k in raw:
                bar = Bar(
                    time=datetime.datetime.fromtimestamp(k[0] / 1000),
                    open=float(k[1]), high=float(k[2]),
                    low=float(k[3]), close=float(k[4]),
                    volume=float(k[5])
                )
                batch.append(bar)
            
            # Binance返回顺序: 旧→新, 直接append保持正序
            for bar in batch:
                if not all_bars or bar.time < all_bars[0].time:
                    all_bars.insert(0, bar)
                else:
                    all_bars.append(bar)
            
            remaining -= take
        
        # 最终按时间正序排序并去重
        seen = set()
        deduped = []
        for b in sorted(all_bars, key=lambda x: x.time):
            ts = b.time.timestamp()
            if ts not in seen:
                seen.add(ts)
                deduped.append(b)
        
        print(f"  ✅ 获取 {len(deduped)} 根 {timeframe} K线 [{self.symbol}]"
              f"  ({deduped[0].time.date()} ~ {deduped[-1].time.date()})" if deduped else "")
        return deduped
    
    def get_latest_price(self) -> float:
        """获取当前最新价格"""
        bars = self._fetch_kline("1m", limit=1)
        if bars:
            return float(bars[0][4])
        return 0.0


# ======================================================================
#  3. 技术指标计算
# ======================================================================

def calc_ema(data: list[float], period: int) -> list[float]:
    """计算EMA"""
    if len(data) < period:
        return [0.0] * len(data)
    
    k = 2.0 / (period + 1.0)
    ema = [0.0] * len(data)
    ema[0] = data[0]
    
    for i in range(1, len(data)):
        ema[i] = data[i] * k + ema[i-1] * (1.0 - k)
    
    return ema

def calc_sma(data: list[float], period: int) -> list[float]:
    """计算SMA"""
    if len(data) < period:
        return [0.0] * len(data)
    
    sma = [0.0] * len(data)
    for i in range(period - 1, len(data)):
        sma[i] = sum(data[i - period + 1 : i + 1]) / period
    return sma

def calc_rsi(data: list[float], period: int = 14) -> list[float]:
    """计算RSI"""
    if len(data) < period + 1:
        return [0.0] * len(data)
    
    rsi = [50.0] * len(data)
    gains, losses = [], []
    
    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(data)):
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
        
        if i < len(data) - 1:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    return rsi

def calc_adx(high: list[float], low: list[float], close: list[float],
             period: int = 14) -> list[float]:
    """计算ADX"""
    n = len(high)
    if n < period * 2:
        return [0.0] * n
    
    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i-1]),
                    abs(low[i] - close[i-1]))
        plus_dm[i] = max(high[i] - high[i-1], 0) if high[i] - high[i-1] > low[i-1] - low[i] else 0
        minus_dm[i] = max(low[i-1] - low[i], 0) if low[i-1] - low[i] > high[i] - high[i-1] else 0
    
    # Smoothed
    atr = [0.0] * n
    plus = [0.0] * n
    minus = [0.0] * n
    atr[period] = sum(tr[1:period+1]) / period
    plus[period] = sum(plus_dm[1:period+1]) / period
    minus[period] = sum(minus_dm[1:period+1]) / period
    
    for i in range(period + 1, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        plus[i] = (plus[i-1] * (period - 1) + plus_dm[i]) / period
        minus[i] = (minus[i-1] * (period - 1) + minus_dm[i]) / period
    
    # DI and ADX
    di_plus = [0.0] * n
    di_minus = [0.0] * n
    dx = [0.0] * n
    adx = [0.0] * n
    
    for i in range(period, n):
        if atr[i] > 0:
            di_plus[i] = 100.0 * plus[i] / atr[i]
            di_minus[i] = 100.0 * minus[i] / atr[i]
        di_diff = abs(di_plus[i] - di_minus[i])
        di_sum = di_plus[i] + di_minus[i]
        dx[i] = 100.0 * di_diff / di_sum if di_sum > 0 else 0
    
    # Smooth DX to get ADX
    adx[period * 2 - 1] = sum(dx[period:period * 2]) / period
    for i in range(period * 2, n):
        adx[i] = (adx[i-1] * (period - 1) + dx[i]) / period
    
    return adx

def calc_atr(high: list[float], low: list[float], close: list[float],
             period: int = 14) -> list[float]:
    """计算ATR"""
    n = len(high)
    if n < period + 1:
        return [0.0] * n
    
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i-1]),
                    abs(low[i] - close[i-1]))
    
    atr = [0.0] * n
    atr[period] = sum(tr[1:period+1]) / period
    for i in range(period + 1, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    
    return atr


# ======================================================================
#  4. 策略库
# ======================================================================

class StrategyResult:
    def __init__(self):
        self.signal = 0   # 1=买, -1=卖, 0=持仓/观望
        self.data = {}    # 策略计算出的指标值

class BaseStrategy:
    """策略基类"""
    name = "base"
    
    def __init__(self):
        self.bars: list[Bar] = []
    
    def on_data(self, bars: list[Bar]) -> StrategyResult:
        """传入新K线数组(最新在末尾)，返回信号"""
        self.bars = bars
        return StrategyResult()
    
    def desc(self) -> str:
        return self.name


# ----- 策略1: H4 EMA20 -----
class H4EMA20(BaseStrategy):
    name = "H4 EMA20 趋势跟踪"
    
    def on_data(self, bars: list[Bar]) -> StrategyResult:
        r = StrategyResult()
        closes = [b.close for b in bars]
        ema20 = calc_ema(closes, 20)
        
        if len(bars) < 22:
            return r
        
        curr_ema = ema20[-1]
        prev_ema = ema20[-2]
        price = closes[-1]
        prev_price = closes[-2]
        
        # 趋势: 收盘价在EMA上方 + EMA向上
        bull = price > curr_ema and prev_price > prev_ema and curr_ema > prev_ema
        bear = price < curr_ema and prev_price < prev_ema and curr_ema < prev_ema
        
        if bull:
            r.signal = 1
        elif bear:
            r.signal = -1
        
        r.data = {"ema20": curr_ema}
        return r


# ----- 策略2: EMA Ribbon (H4) -----
class EMARibbon(BaseStrategy):
    name = "H4 EMA Ribbon 排列 + ADX"
    
    def on_data(self, bars: list[Bar]) -> StrategyResult:
        r = StrategyResult()
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        
        ema10 = calc_ema(closes, 10)
        ema20 = calc_ema(closes, 20)
        ema30 = calc_ema(closes, 30)
        ema50 = calc_ema(closes, 50)
        adx = calc_adx(highs, lows, closes, 14)
        
        if len(bars) < 55:
            return r
        
        # 多头排列: 10>20>30>50
        bull = (ema10[-1] > ema20[-1] > ema30[-1] > ema50[-1])
        # 空头排列: 10<20<30<50
        bear = (ema10[-1] < ema20[-1] < ema30[-1] < ema50[-1])
        
        adx_val = adx[-1]
        
        if bull and adx_val > 20:
            r.signal = 1
        elif bear and adx_val > 20:
            r.signal = -1
        
        r.data = {
            "ema10": ema10[-1], "ema20": ema20[-1],
            "ema30": ema30[-1], "ema50": ema50[-1],
            "adx": adx_val
        }
        return r


# ----- 策略3: 日线均值回归(Daily Mean Rev) -----
class DailyMeanRev(BaseStrategy):
    name = "日线均值回归"
    
    def on_data(self, bars: list[Bar]) -> StrategyResult:
        r = StrategyResult()
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        
        ema20 = calc_ema(closes, 20)
        atr = calc_atr(highs, lows, closes, 14)
        
        if len(bars) < 25:
            return r
        
        price = closes[-1]
        ma = ema20[-1]
        atr_val = atr[-1]
        
        if ma <= 0 or atr_val <= 0:
            return r
        
        dist = (price - ma) / ma  # 价格偏离EMA的比例
        
        # 日线斜率
        slope = (ema20[-1] - ema20[-6]) / ema20[-6] if len(ema20) > 6 else 0
        
        # 多头趋势 + 价格跌破EMA下沿(回调买入)
        if slope > 0.0005 and dist < -0.01:
            r.signal = 1
        # 空头趋势 + 价格涨破EMA上沿(反弹卖出)
        elif slope < -0.0005 and dist > 0.01:
            r.signal = -1
        
        r.data = {"ema20": ma, "atr": atr_val, "dist%": dist * 100}
        return r


# ----- 策略4: RSI + EMA 共振 -----
class RSI_EMA(BaseStrategy):
    name = "RSI+EMA 共振"
    
    def on_data(self, bars: list[Bar]) -> StrategyResult:
        r = StrategyResult()
        closes = [b.close for b in bars]
        ema20 = calc_ema(closes, 20)
        rsi = calc_rsi(closes, 14)
        
        if len(bars) < 25:
            return r
        
        price = closes[-1]
        ma = ema20[-1]
        rsi_val = rsi[-1]
        
        # 多头: 价格>EMA + RSI>50(非超买)
        if price > ma and 50 < rsi_val < 70:
            r.signal = 1
        # 空头: 价格<EMA + RSI<50(非超卖)
        elif price < ma and 30 < rsi_val < 50:
            r.signal = -1
        
        r.data = {"ema20": ma, "rsi": rsi_val}
        return r


# ----- 获取所有策略 -----
def get_all_strategies() -> list[BaseStrategy]:
    return [
        H4EMA20(),
        EMARibbon(),
        DailyMeanRev(),
        RSI_EMA(),
    ]


# ======================================================================
#  5. 回测引擎
# ======================================================================

class Backtester:
    """
    回测引擎
    
    用法:
        fetcher = DataFetcher()
        bars = fetcher.fetch_bars("4h", 500)
        strategy = H4EMA20()
        result = Backtester.run(bars, strategy, initial_capital=10000)
    """
    
    @staticmethod
    def run(bars: list[Bar], strategy: BaseStrategy,
            initial_capital: float = 10000.0,
            risk_per_trade: float = 25.0,
            trail_trigger: float = 60.0,
            trail_back: float = 25.0,
            sl_atr: float = 1.5) -> BacktestResult:
        """运行回测"""
        
        result = BacktestResult()
        if len(bars) < 50:
            print("  ⚠️ 数据不足50根，无法回测")
            return result
        
        # 预计算指标
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        atr = calc_atr(highs, lows, closes, 14)
        
        # 状态
        position = 0        # 0=空仓, 1=多头, -1=空头
        entry_price = 0.0
        entry_bar = 0
        trail_active = False
        trail_high = 0.0
        trade = None
        equity = initial_capital
        equity_curve = [EquityPoint(bars[0].time, equity, 0)]
        peak_equity = equity
        
        for i in range(len(bars)):
            bar = bars[i]
            current_bars = bars[:i+1]
            
            # 检查是否有足够的ATR数据
            atr_val = atr[i]
            if atr_val <= 0:
                equity_curve.append(EquityPoint(bar.time, equity,
                    (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0))
                continue
            
            # 动态手数 (BTC 单位)
            # BTCUSDT: 1 lot = 1 BTC, 止损距离(价格点数) × 手数 = 风险金额
            sl_pts = atr_val * sl_atr
            lots = max(0.01, min(0.1, risk_per_trade / sl_pts))
            lots = round(lots, 2)
            
            # ====== 有持仓 ======
            if position != 0:
                # 止损检查
                sl_price = (entry_price - sl_pts) if position == 1 else (entry_price + sl_pts)
                
                exit_triggered = False
                exit_reason = ""
                
                if position == 1 and bar.low <= sl_price:
                    exit_price = sl_price
                    exit_triggered = True
                    exit_reason = "止损"
                elif position == -1 and bar.high >= sl_price:
                    exit_price = sl_price
                    exit_triggered = True
                    exit_reason = "止损"
                
                # 追踪止盈
                if not exit_triggered:
                    if position == 1:
                        if not trail_active and (bar.close - entry_price) >= trail_trigger:
                            trail_active = True
                            trail_high = bar.high
                        if trail_active:
                            if bar.high > trail_high:
                                trail_high = bar.high
                            if trail_high - bar.close >= trail_back:
                                exit_price = bar.close
                                exit_triggered = True
                                exit_reason = "追踪止盈"
                    else:
                        if not trail_active and (entry_price - bar.close) >= trail_trigger:
                            trail_active = True
                            trail_high = bar.low
                        if trail_active:
                            if bar.low < trail_high:
                                trail_high = bar.low
                            if bar.close - trail_high >= trail_back:
                                exit_price = bar.close
                                exit_triggered = True
                                exit_reason = "追踪止盈"
                
                # 策略反转检查
                if not exit_triggered:
                    sig = strategy.on_data(current_bars)
                    if sig.signal != 0 and sig.signal != position:
                        exit_price = bar.close
                        exit_triggered = True
                        exit_reason = "策略反转"
                
                if exit_triggered:
                    pnl = (exit_price - entry_price) * lots if position == 1 \
                          else (entry_price - exit_price) * lots
                    equity += pnl
                    
                    if trade:
                        trade.exit_time = bar.time
                        trade.exit_price = exit_price
                        trade.pnl = pnl
                        trade.pnl_pct = pnl / initial_capital * 100
                        trade.exit_reason = exit_reason
                    
                    position = 0
                    trail_active = False
                    trail_high = 0.0
            
            # ====== 空仓检查入场 ======
            if position == 0:
                sig = strategy.on_data(current_bars)
                if sig.signal != 0:
                    position = sig.signal
                    entry_price = bar.close
                    entry_bar = i
                    trail_active = False
                    
                    trade = Trade(
                        entry_time=bar.time,
                        side="BUY" if sig.signal == 1 else "SELL",
                        entry_price=bar.close,
                        size=lots
                    )
                    result.trades.append(trade)
            
            # 记录净值
            if position != 0:
                unrealized = (bar.close - entry_price) * lots if position == 1 \
                             else (entry_price - bar.close) * lots
                current_equity = equity + unrealized  # 包含浮盈浮亏
            else:
                current_equity = equity
            
            if current_equity > peak_equity:
                peak_equity = current_equity
            
            dd = (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0
            equity_curve.append(EquityPoint(bar.time, current_equity, dd))
        
        # ====== 平掉最后持仓 ======
        if position != 0:
            pnl = (bars[-1].close - entry_price) * lots if position == 1 \
                  else (entry_price - bars[-1].close) * lots
            equity += pnl
            if trade:
                trade.exit_time = bars[-1].time
                trade.exit_price = bars[-1].close
                trade.pnl = pnl
                trade.pnl_pct = pnl / initial_capital * 100
                trade.exit_reason = "结束"
        
        # ====== 计算统计 ======
        result.equity_curve = equity_curve
        result.total_pnl = equity - initial_capital
        result.total_pnl_pct = (equity - initial_capital) / initial_capital * 100
        result.total_trades = len([t for t in result.trades if t.exit_time is not None])
        result.win_trades = len([t for t in result.trades if t.pnl > 0])
        result.lose_trades = len([t for t in result.trades if t.pnl < 0])
        result.win_rate = (result.win_trades / result.total_trades * 100) if result.total_trades > 0 else 0
        
        # 最大回撤
        result.max_drawdown = max((ep.drawdown for ep in equity_curve), default=0)
        
        # 盈亏统计
        wins = [t.pnl for t in result.trades if t.pnl > 0]
        losses = [t.pnl for t in result.trades if t.pnl < 0]
        result.avg_win = np.mean(wins) if wins else 0
        result.avg_loss = abs(np.mean(losses)) if losses else 0
        result.profit_factor = abs(sum(wins) / sum(losses)) if sum(losses) != 0 else float('inf')
        
        # 夏普率(简化)
        returns = [t.pnl for t in result.trades]
        if returns and np.std(returns) > 0:
            result.sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        
        return result


# ======================================================================
#  6. 可视化输出
# ======================================================================

def plot_result(result: BacktestResult, strategy_name: str,
                timeframe: str, capital: float, save_path: str = ""):
    """生成回测结果图表"""
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    
    if not result.equity_curve:
        print("  ⚠️ 无数据可绘图")
        return
    
    times = [ep.time for ep in result.equity_curve]
    equities = [ep.equity for ep in result.equity_curve]
    dds = [ep.drawdown for ep in result.equity_curve]
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), gridspec_kw={
        "height_ratios": [3, 1, 1.5]
    })
    fig.suptitle(f"📊 {strategy_name}  |  {timeframe}  |  初始 ${capital:,.0f}",
                 fontsize=14, fontweight="bold")
    
    # 净值曲线
    ax1 = axes[0]
    ax1.plot(times, equities, color="#2196F3", linewidth=1.5, label="净值")
    ax1.axhline(y=capital, color="#999", linestyle="--", alpha=0.5, label=f"本金 ${capital:,.0f}")
    ax1.fill_between(times, capital, equities, where=[e >= capital for e in equities],
                     color="#4CAF50", alpha=0.15)
    ax1.fill_between(times, capital, equities, where=[e < capital for e in equities],
                     color="#F44336", alpha=0.1)
    ax1.set_ylabel("账户净值 ($)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    
    # 交易标记
    for t in result.trades:
        if t.exit_time:
            color = "#4CAF50" if t.pnl > 0 else "#F44336"
            ax1.axvline(x=t.entry_time, color=color, alpha=0.15, linewidth=0.5)
    
    # 回撤图
    ax2 = axes[1]
    ax2.fill_between(times, 0, dds, color="#F44336", alpha=0.3)
    ax2.plot(times, dds, color="#F44336", linewidth=1)
    ax2.set_ylabel("回撤 (%)")
    ax2.set_ylim(bottom=0)
    ax2.invert_yaxis()
    ax2.grid(True, alpha=0.3)
    
    # 统计面板
    ax3 = axes[2]
    ax3.axis("off")
    
    stats_text = (
        f"💰 总盈亏: ${result.total_pnl:+,.2f}  ({result.total_pnl_pct:+.2f}%)\n"
        f"📈 交易次数: {result.total_trades}  |  "
        f"✅ 胜率: {result.win_rate:.1f}%\n"
        f"🏆 平均盈利: ${result.avg_win:+.2f}  |  "
        f"💀 平均亏损: -${result.avg_loss:.2f}\n"
        f"📉 最大回撤: {result.max_drawdown:.2f}%  |  "
        f"⚡ 夏普率: {result.sharpe:.2f}\n"
        f"🎯 盈亏比: {result.profit_factor:.2f}  |  "
        f"💰 净收益: ${result.total_pnl:+,.2f}"
    )
    
    ax3.text(0.5, 0.5, stats_text, transform=ax3.transAxes,
             fontsize=13, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=1", facecolor="#f5f5f5", edgecolor="#ddd"))
    
    plt.tight_layout()
    
    out_path = save_path or f"btc_backtest_{strategy_name.replace(' ', '_')}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n  📷 图表已保存: {out_path}")
    plt.show()


def print_result(result: BacktestResult, strategy_name: str):
    """终端输出回测结果"""
    print(f"\n{'='*55}")
    print(f"  📊 {strategy_name}")
    print(f"{'='*55}")
    print(f"  💰 净盈亏:     ${result.total_pnl:>+8,.2f}  ({result.total_pnl_pct:>+6.2f}%)")
    print(f"  📈 交易次数:   {result.total_trades:>5}")
    print(f"  ✅ 胜率:       {result.win_rate:>5.1f}%")
    print(f"  🏆 平均盈利:   ${result.avg_win:>+8,.2f}")
    print(f"  💀 平均亏损:   ${result.avg_loss:>8,.2f}")
    print(f"  📉 最大回撤:   {result.max_drawdown:>5.2f}%")
    print(f"  🎯 盈亏比:     {result.profit_factor:>5.2f}")
    print(f"  ⚡ 夏普率:     {result.sharpe:>5.2f}")
    print(f"{'='*55}")
    
    # 最近5笔交易
    trades = [t for t in result.trades if t.exit_time]
    if trades:
        print(f"\n  📋 最近5笔交易:")
        for t in trades[-5:]:
            side_mark = "🟢" if t.side == "BUY" else "🔴"
            pnl_mark = "✅" if t.pnl > 0 else "💀"
            print(f"    {pnl_mark} {side_mark} "
                  f"{t.entry_time.strftime('%m/%d %H:00')} → "
                  f"{t.exit_time.strftime('%m/%d %H:00')}  "
                  f"${t.pnl:>+8,.2f}  [{t.exit_reason}]")
    
    print()


# ======================================================================
#  7. 实时行情监控
# ======================================================================

class LiveMonitor:
    """
    实时行情监控 + 策略信号
    
    每1分钟刷新一次，显示所有策略的当前信号
    """
    
    def __init__(self, symbol: str = "BTCUSDT"):
        self.fetcher = DataFetcher(symbol)
        self.symbol = symbol
        self.running = False
    
    def start(self, interval: str = "15m", lookback: int = 200):
        """
        启动实时监控
        
        参数:
            interval: 监控周期(15m/1h/4h)
            lookback: 保留多少根K线
        """
        self.running = True
        strategies = get_all_strategies()
        
        print(f"\n{'='*60}")
        print(f"  🔴 实时行情监控 — {self.symbol}")
        print(f"  周期: {interval}  |  每60秒刷新")
        print(f"  策略数: {len(strategies)}")
        print(f"{'='*60}")
        
        while self.running:
            try:
                bars = self.fetcher.fetch_bars(interval, lookback)
                price = bars[-1].close if bars else 0
                change = ((bars[-1].close - bars[-2].close) / bars[-2].close * 100) \
                         if len(bars) > 1 else 0
                
                # 清屏
                os.system("cls" if os.name == "nt" else "clear")
                
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n{'='*60}")
                print(f"  🔴 BTC/USDT  实时监控  [{now}]")
                print(f"{'='*60}")
                
                change_mark = "🟢" if change >= 0 else "🔴"
                print(f"\n  当前价格: ${price:>8,.2f}  "
                      f"{change_mark} {change:>+.2f}%")
                print(f"  数据: {len(bars)} 根 {interval} K线")
                
                print(f"\n{'─'*60}")
                print(f"  {'策略':<22} {'信号':<8} {'关键指标':<20}")
                print(f"{'─'*60}")
                
                for s in strategies:
                    sig = s.on_data(bars)
                    signal_str = ""
                    if sig.signal == 1:
                        signal_str = "🟢 买入"
                    elif sig.signal == -1:
                        signal_str = "🔴 卖出"
                    else:
                        signal_str = "⚪ 观望"
                    
                    # 显示关键指标
                    indicators = ", ".join([f"{k}={v:.2f}" for k, v in sig.data.items()])
                    print(f"  {s.name:<22} {signal_str:<8} {indicators[:35]:<20}")
                
                print(f"\n  ⏰ {now}  |  下次更新: {datetime.datetime.now().strftime('%H:%M:%S')}")
                print(f"  [按 Ctrl+C 退出]")
                
                # 睡60秒
                for _ in range(60):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                self.running = False
                print("\n\n  👋 已退出")
                break
            except Exception as e:
                print(f"\n  ⚠️ 错误: {e}")
                time.sleep(10)


# ======================================================================
#  8. 主菜单
# ======================================================================

def main_menu():
    """显示主菜单"""
    
    fetcher = DataFetcher()
    all_strategies = get_all_strategies()
    
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        
        print(f"\n{'='*55}")
        print(f"     🤖 BTC 交易策略机器人  v1.0")
        print(f"     Senior Developer @ AI Trading System")
        print(f"{'='*55}")
        print(f"\n  当前品种: BTC/USDT")
        print(f"\n{'─'*55}")
        print(f"  [1] 🔙 历史回测")
        print(f"  [2] 📡 实时行情监控")
        print(f"  [3] 📊 全策略对比回测")
        print(f"  [0] ❌ 退出")
        print(f"{'─'*55}")
        
        choice = input(f"\n  请选择 [0-3]: ").strip()
        
        if choice == "0":
            print("\n  👋 再见!")
            break
        
        elif choice == "1":
            run_single_backtest(fetcher, all_strategies)
        
        elif choice == "2":
            monitor = LiveMonitor()
            monitor.start()
        
        elif choice == "3":
            run_all_backtests(fetcher, all_strategies)
        
        else:
            print("\n  ⚠️ 无效选择")
            time.sleep(1)


def run_single_backtest(fetcher: DataFetcher, strategies: list):
    """单策略回测"""
    
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n{'='*55}")
    print(f"  🔙 历史回测")
    print(f"{'='*55}")
    
    # 选策略
    print(f"\n  可选策略:")
    for i, s in enumerate(strategies):
        print(f"    [{i+1}] {s.name}")
    
    try:
        s_choice = int(input(f"\n  选择策略 [1-{len(strategies)}]: ").strip()) - 1
        strategy = strategies[s_choice]
    except:
        print("  ⚠️ 无效选择")
        time.sleep(1)
        return
    
    # 选周期
    print(f"\n  可选周期: 1m / 5m / 15m / 1h / 4h / 1d")
    tf = input(f"  选择周期 [默认4h]: ").strip() or "4h"
    
    # K线数量
    try:
        count = int(input(f"  K线数量 [默认500]: ").strip() or "500")
    except:
        count = 500
    
    # 本金
    try:
        capital = float(input(f"  初始资金($) [默认10000]: ").strip() or "10000")
    except:
        capital = 10000
    
    print(f"\n  🔄 正在获取数据...")
    bars = fetcher.fetch_bars(tf, count)
    
    if len(bars) < 50:
        input(f"\n  ⚠️ 数据不足 (仅{len(bars)}根)，按回车返回")
        return
    
    print(f"  🔄 正在回测...")
    result = Backtester.run(bars, strategy, initial_capital=capital)
    
    print_result(result, strategy.name)
    plot_result(result, strategy.name, tf, capital)
    
    input(f"\n  按回车返回主菜单...")


def run_all_backtests(fetcher: DataFetcher, strategies: list):
    """全策略对比回测"""
    
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n{'='*55}")
    print(f"  📊 全策略对比回测")
    print(f"{'='*55}")
    
    # 选周期
    print(f"\n  可选周期: 1m / 5m / 15m / 1h / 4h / 1d")
    tf = input(f"  选择周期 [默认4h]: ").strip() or "4h"
    
    try:
        count = int(input(f"  K线数量 [默认500]: ").strip() or "500")
    except:
        count = 500
    
    try:
        capital = float(input(f"  初始资金($) [默认10000]: ").strip() or "10000")
    except:
        capital = 10000
    
    print(f"\n  🔄 正在获取数据...")
    bars = fetcher.fetch_bars(tf, count)
    
    if len(bars) < 50:
        input(f"\n  ⚠️ 数据不足 (仅{len(bars)}根)，按回车返回")
        return
    
    results = []
    for strategy in strategies:
        print(f"  🔄 回测中: {strategy.name}")
        result = Backtester.run(bars, strategy, initial_capital=capital)
        results.append((strategy, result))
    
    # 排序: 按净盈亏
    results.sort(key=lambda x: x[1].total_pnl, reverse=True)
    
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n{'='*65}")
    print(f"  📊 全策略对比 — {tf}  |  {len(bars)}根K线")
    print(f"{'='*65}")
    print(f"  {'排名':<4} {'策略':<22} {'净盈亏':<12} {'胜率':<8} {'回撤':<8} {'交易':<6}")
    print(f"{'─'*65}")
    
    for i, (s, r) in enumerate(results):
        rank = f"#{i+1}" if i == 0 else f" #{i+1}"
        print(f"  {rank:<4} {s.name:<22} ${r.total_pnl:>+8,.2f} "
              f"{r.win_rate:>5.1f}% {r.max_drawdown:>5.1f}% {r.total_trades:>4}")
    
    print(f"{'─'*65}")
    
    # 显示冠军详情
    best_s, best_r = results[0]
    print(f"\n  🏆 最佳策略: {best_s.name}")
    print_result(best_r, best_s.name)
    plot_result(best_r, best_s.name, tf, capital)
    
    input(f"\n  按回车返回主菜单...")


# ======================================================================
#  9. Web 操作面板 (Flask + HTML)
# ======================================================================

def run_api_server():
    """
    Web 操作面板 + API服务器 + MT5自动交易
    """
    try:
        from flask import Flask, jsonify, request, render_template_string
    except ImportError:
        print("  ⚠️ 需要安装 flask: pip install flask")
        return
    
    import threading
    import pickle
    
    app = Flask(__name__)
    
    # ===== 本地SQLite数据源 (彻底替代MT5/Binance) =====
    MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
    MT5_SYMBOL = "BTCUSD"
    DB_PATH = "D:/BTC/mt5_data.db"
    
    # 时间框架映射到分钟数
    TF_MINUTES = {"1m":1,"5m":5,"15m":15,"30m":30,"1h":60,"4h":240,"1d":1440}
    
    def db_get_bars(tf_str: str, count: int) -> list:
        """从本地SQLite获取K线(最旧在前), 自动从1m合成大周期"""
        import sqlite3
        try:
            conn = sqlite3.connect(DB_PATH)
            tf_min = TF_MINUTES.get(tf_str, 60)
            
            # 从1m数据库读取原始数据
            need_minutes = tf_min * (count + 3)
            rows = conn.execute(
                "SELECT time,open,high,low,close,tick_volume FROM bars_1m ORDER BY time ASC LIMIT -1 OFFSET (SELECT MAX(0, COUNT(*)-?) FROM bars_1m)",
                (need_minutes,)
            ).fetchall()
            conn.close()
            
            if len(rows) < tf_min * 2:
                return []  # 数据不够
            
            # 合成大周期K线
            bars = []
            bucket = []
            bucket_time = None
            slot_sec = tf_min * 60
            
            for row in rows:
                t_str, o, h, l, c, v = row
                t = datetime.datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                slot = t.replace(second=0, microsecond=0)
                slot_min = (slot.minute // tf_min) * tf_min
                slot_key = slot.replace(minute=slot_min)
                
                if tf_min >= 60:  # 小时级别
                    slot_key = slot.replace(minute=0)
                if tf_min >= 1440:  # 日线
                    slot_key = slot.replace(hour=0, minute=0)
                
                if slot_key != bucket_time and bucket:
                    bars.append(Bar(
                        time=bucket_time, open=float(bucket[0][1]),
                        high=max(float(b[2]) for b in bucket),
                        low=min(float(b[3]) for b in bucket),
                        close=float(bucket[-1][4]),
                        volume=sum(int(b[5]) for b in bucket if b[5])
                    ))
                    bucket = []
                
                if not bucket:
                    bucket_time = slot_key
                bucket.append(row)
            
            if bucket:
                bars.append(Bar(
                    time=bucket_time, open=float(bucket[0][1]),
                    high=max(float(b[2]) for b in bucket),
                    low=min(float(b[3]) for b in bucket),
                    close=float(bucket[-1][4]),
                    volume=sum(int(b[5]) for b in bucket if b[5])
                ))
            
            return bars[-count:] if len(bars) >= 1 else []
        except Exception as e:
            print(f"  ⚠️ DB {tf_str}: {e}")
            return []
    
    fetcher = DataFetcher()  # 保留作为回测时的降级
    strategies = get_all_strategies()
    
    bars_4h = []
    bars_1h = []
    bars_1d = []
    last_update = 0
    last_result = {}
    
    # MT5自动交易状态
    auto_trade_enabled = False
    auto_trade_last_signal = 0
    auto_trade_status = "未启动"
    auto_trade_log = []
    
    def refresh_data():
        nonlocal bars_4h, bars_1h, bars_1d, last_update
        now = time.time()
        if now - last_update < 120:
            return
        try:
            # 全部从MT5获取
            bars_4h = db_get_bars("4h", 200)
            bars_1h = db_get_bars("1h", 100)
            bars_1d = db_get_bars("1d", 60)
            last_update = now
        except:
            pass
    
    def get_real_time_price() -> float:
        """从 MT5 获取 BTCUSD 实时价格 (Bid价，即卖出价)"""
        try:
            import MetaTrader5 as mt5
            if mt5.initialize(path=MT5_PATH):
                mt5.symbol_select(MT5_SYMBOL, True)
                tick = mt5.symbol_info_tick(MT5_SYMBOL)
                mt5.shutdown()
                if tick:
                    return tick.bid  # Bid价 = 当前可卖出的价格
            return 0.0
        except:
            # MT5不可用时降级到币安
            try:
                import urllib.request
                url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=3) as resp:
                    return float(json.loads(resp.read())["price"])
            except:
                return 0.0
    
    # ======================== API ========================
    
    # ----- MT5 自动交易 -----
    MT5_MAGIC = 60107
    RISK_PER_TRADE = 10.0
    SL_ATR = 1.5
    
    def mt5_trade(action: str, price: float, sl_price: float) -> str:
        """在MT5上执行交易 — 通过subprocess调用来避免线程安全问题"""
        import subprocess
        import sys as sys_module
        
        trade_code = f'''
import MetaTrader5 as mt5, json
r = mt5.initialize(path=r"{MT5_PATH}")
if not r:
    print(json.dumps({{"error": "init failed"}}))
else:
    mt5.symbol_select("{MT5_SYMBOL}", True)
    tick = mt5.symbol_info_tick("{MT5_SYMBOL}")
    if not tick:
        print(json.dumps({{"error": "no tick"}}))
    else:
        msg = []
        
        # 平现有仓位
        pos = mt5.positions_get(symbol="{MT5_SYMBOL}")
        if pos:
            p = pos[0]
            side = "BUY" if p.type == 0 else "SELL"
            ct = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
            cp = tick.bid if p.type == 0 else tick.ask
            req = {{
                "action": mt5.TRADE_ACTION_DEAL, "symbol": "{MT5_SYMBOL}",
                "volume": p.volume, "type": ct, "position": p.ticket,
                "price": cp, "deviation": 50, "magic": {MT5_MAGIC},
                "comment": "Close", "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }}
            rr = mt5.order_send(req)
            if rr and rr.retcode == mt5.TRADE_RETCODE_DONE:
                msg.append(f"平{{side}}(${{p.profit:.2f}})")
            else:
                msg.append(f"平仓失败")
        
        if "{action}" != "CLOSE":
            is_buy = {action == "BUY"}
            ep = tick.ask if is_buy else tick.bid
            sl_d = abs(ep - {sl_price})
            lot = max(0.01, min(0.1, round({RISK_PER_TRADE} / sl_d, 2))) if sl_d > 0 else 0.01
            req = {{
                "action": mt5.TRADE_ACTION_DEAL, "symbol": "{MT5_SYMBOL}",
                "volume": lot, "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                "price": ep, "sl": {sl_price}, "tp": 0,
                "deviation": 50, "magic": {MT5_MAGIC},
                "comment": "RSI_{action}", "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }}
            rr = mt5.order_send(req)
            if rr and rr.retcode == mt5.TRADE_RETCODE_DONE:
                msg.append(f"开{{'BUY' if is_buy else 'SELL'}} {{lot:.2f}}lot @${{ep:.2f}}")
            else:
                err = getattr(rr, 'retcode', 'None')
                msg.append(f"开仓失败({{err}})")
        
        print(json.dumps({{"result": "|".join(msg)}}))
    mt5.shutdown()
'''
        try:
            r = subprocess.run(
                [sys_module.executable, "-c", trade_code],
                capture_output=True, text=True, timeout=30
            )
            out = r.stdout.strip()
            if out:
                try:
                    d = json.loads(out)
                    return d.get("result", d.get("error", out[:50]))
                except:
                    return out[:50]
            return r.stderr.strip()[:50] or "无返回"
        except subprocess.TimeoutExpired:
            return "交易超时"
        except Exception as e:
            return f"异常: {e}"
    
    def auto_trade_loop():
        """自动交易: ADX过滤 + MACD确认 + 移动止损"""
        nonlocal auto_trade_enabled, auto_trade_last_signal, auto_trade_status, auto_trade_log
        auto_trade_log = []
        def alog(m):
            t = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{t}] {m}"
            auto_trade_log.append(line)
            if len(auto_trade_log) > 100: auto_trade_log.pop(0)
            print(f"  🤖 {m}")
        
        alog("启动 · RSI+EMA+ADX+MACD 三重确认 · 移动止损")
        
        import MetaTrader5 as mt5_live
        
        # 移动止损参数
        TRAIL_START = 300.0   # 浮盈>$300开始移动止损($BTCUSD点约$3)
        TRAIL_DIST = 200.0    # 移动止损距离$200($2)
        MIN_PROFIT = 3.0      # 最小浮盈
        SLEEP_SEC = 120
        
        # 记录已开仓的入场价
        _entry_price = 0
        _trail_sl = 0
        
        while auto_trade_enabled:
            try:
                if not mt5_live.initialize(path=MT5_PATH):
                    time.sleep(60); continue
                mt5_live.symbol_select(MT5_SYMBOL, True)
                
                pos = mt5_live.positions_get(symbol=MT5_SYMBOL)
                has_pos = bool(pos and len(pos) > 0)
                tick = mt5_live.symbol_info_tick(MT5_SYMBOL)
                live_price = tick.bid if tick else 0
                
                # ===== 有持仓: 移动止损 =====
                if has_pos:
                    p = pos[0]
                    profit = p.profit if hasattr(p, 'profit') else 0
                    side = "BUY" if p.type == 0 else "SELL"
                    
                    # 首次检测到持仓,记录入场价
                    if _entry_price == 0:
                        _entry_price = p.price_open
                        _trail_sl = p.sl
                    
                    if profit >= MIN_PROFIT:
                        # 移动止损: 价格向有利方向移动时, 移动SL
                        if side == "BUY":
                            new_sl = live_price - TRAIL_DIST
                            if new_sl > _trail_sl and new_sl > p.sl:
                                _trail_sl = new_sl
                        else:
                            new_sl = live_price + TRAIL_DIST
                            if new_sl < _trail_sl and new_sl < p.sl:
                                _trail_sl = new_sl
                        
                        auto_trade_status = f"{side} 浮盈${profit:.2f} SL=${_trail_sl:.0f}"
                    else:
                        auto_trade_status = f"{side} 浮盈${profit:.2f} (待${MIN_PROFIT})"
                    
                    mt5_live.shutdown()
                    time.sleep(SLEEP_SEC)
                    continue
                
                _entry_price = 0; _trail_sl = 0
                
                # ===== 无持仓: 三重确认入场 =====
                mt5_live.shutdown()
                
                # 从DB获取数据
                bars_4h = db_get_bars("4h", 30)
                
                # 先计算4h级别的MACD和ADX (用于整体过滤)
                macd_bull = True   # 默认MACD多头
                adx_strong = False # 默认ADX不强制
                if len(bars_4h) >= 28:
                    cl4 = [b.close for b in bars_4h]
                    ema12 = calc_ema(cl4, 12)
                    ema26 = calc_ema(cl4, 26)
                    macd_line = [ema12[i]-ema26[i] for i in range(len(cl4))]
                    signal_line = calc_ema(macd_line, 9)
                    macd_bull = macd_line[-1] > signal_line[-1]
                    # ADX
                    h4 = [b.high for b in bars_4h]; l4 = [b.low for b in bars_4h]
                    adx4 = calc_adx(h4, l4, cl4, 14)[-1]
                    adx_strong = adx4 > 20
                
                # 多周期共振 (每个周期加MACD检查)
                tf_list = [("5m",5),("15m",15),("30m",30),("1h",60),("4h",240)]
                votes = []
                atr_val = 2000
                for nm, mins in tf_list:
                    bars = db_get_bars(nm, 50)
                    if len(bars) < 30: continue
                    cl = [b.close for b in bars]; hi = [b.high for b in bars]; lo = [b.low for b in bars]
                    ema20 = calc_ema(cl, 20); rsi = calc_rsi(cl, 14)
                    p, e, r = cl[-1], ema20[-1], rsi[-1]
                    
                    # RSI+EMA基础信号
                    sig = 1 if (p>e and 50<r<70) else (-1 if (p<e and 30<r<50) else 0)
                    
                    # MACD确认: 同向才计入
                    if sig != 0 and len(cl) >= 28:
                        e12 = calc_ema(cl, 12); e26 = calc_ema(cl, 26)
                        ml = [e12[i]-e26[i] for i in range(len(cl))]
                        sl = calc_ema(ml, 9)
                        if (sig == 1 and ml[-1] <= sl[-1]) or (sig == -1 and ml[-1] >= sl[-1]):
                            sig = 0  # MACD不确认, 降级为观望
                    
                    votes.append(sig)
                    if nm == "4h" and len(bars) >= 15:
                        atr_val = calc_atr(hi, lo, cl, 14)[-1]
                
                buys = sum(1 for v in votes if v == 1)
                sells = sum(1 for v in votes if v == -1)
                sl_dist = max(atr_val, 500) * 1.5
                
                # ADX弱趋势时降低开仓阈值
                threshold = 2 if adx_strong else 3
                
                # ML预测
                ml_signal = 0; ml_conf = 0
                try:
                    bars_1h = db_get_bars("1h", 30)
                    if len(bars_1h) >= 28:
                        clh = [b.close for b in bars_1h]; p = clh[-1]
                        feats = [1 if clh[-1]>clh[-2] else 0, 1 if clh[-1]>clh[0] else 0,
                                 (p-min(clh))/(max(clh)-min(clh)+0.01),
                                 (max(bars_1h[-2].high,bars_1h[-1].high)-min(bars_1h[-2].low,bars_1h[-1].low))/p,
                                 float(np.std(clh[-6:])/p), float(np.std(clh)/p)]
                        if os.path.exists("kline_model.pkl"):
                            with open("kline_model.pkl","rb") as f:
                                prob=pickle.load(f)["model"].predict_proba([feats])[0]
                            ml_signal = 1 if prob[1]>prob[0] else -1
                            ml_conf = max(prob)
                except Exception as e:
                    pass
                
                # ===== 5. ADX+MACD+ML+共振 四重确认 → 开仓 =====
                ml_text = f" ML:{'🟢' if ml_signal==1 else '🔴'}{ml_conf*100:.0f}%" if ml_signal != 0 else ""
                adx_text = f" ADX:{'强' if adx_strong else '弱'}趋势" if len(bars_4h)>=28 else ""
                macd_text = f" MACD:{'多' if macd_bull else '空'}" if len(bars_4h)>=28 else ""
                
                # 入场条件: 共振≥阈值 + ML不反对 + MACD不反对
                if buys >= threshold and ml_signal >= 0 and macd_bull:
                    action = "BUY"
                    sl_price = live_price - sl_dist
                    result = mt5_trade(action, live_price, sl_price)
                    alog(f"📊 共振{buys}/5看涨{adx_text}{macd_text}{ml_text} → {result}")
                    if "开仓" in result and "失败" not in result:
                        auto_trade_last_signal = 1; _entry_price = live_price; _trail_sl = sl_price
                        auto_trade_status = f"BUY @${live_price:.0f} SL=${sl_price:.0f}"
                    else:
                        auto_trade_status = f"开仓失败"
                
                elif sells >= threshold and ml_signal <= 0 and not macd_bull:
                    action = "SELL"
                    sl_price = live_price + sl_dist
                    result = mt5_trade(action, live_price, sl_price)
                    alog(f"📊 共振{sells}/5看跌{adx_text}{macd_text}{ml_text} → {result}")
                    if "开仓" in result and "失败" not in result:
                        auto_trade_last_signal = -1; _entry_price = live_price; _trail_sl = sl_price
                        auto_trade_status = f"SELL @${live_price:.0f} SL=${sl_price:.0f}"
                    else:
                        auto_trade_status = f"开仓失败"
                else:
                    auto_trade_status = f"观望 {buys}买/{sells}卖/5{macd_text}{adx_text}"
            
            except Exception as e:
                import traceback
                alog(f"异常: {e}")
                try: mt5_live.shutdown()
                except: pass
            
            time.sleep(SLEEP_SEC)
        
        alog("自动交易已停止")
    
    @app.route("/api/auto_trade")
    def api_auto_trade():
        nonlocal auto_trade_enabled, auto_trade_status, auto_trade_log
        cmd = request.args.get("cmd", "status")
        
        if cmd == "start":
            if not auto_trade_enabled:
                auto_trade_enabled = True
                t = threading.Thread(target=auto_trade_loop, daemon=True)
                t.start()
                return jsonify({"status": "started"})
            return jsonify({"status": "already_running"})
        
        elif cmd == "stop":
            auto_trade_enabled = False
            return jsonify({"status": "stopping"})
        
        return jsonify({
            "enabled": auto_trade_enabled,
            "status": auto_trade_status,
            "last_signal": auto_trade_last_signal,
            "logs": auto_trade_log[-20:],
        })
    
    # ----- MT5持仓实时查询 -----
    @app.route("/api/position")
    def api_position():
        """查询MT5实时持仓和K线数据"""
        try:
            import MetaTrader5 as mt5_p
            mt5_p.initialize(path=MT5_PATH)
            mt5_p.symbol_select(MT5_SYMBOL, True)
            
            result = {"has_position": False, "balance": 0, "equity": 0}
            
            acc = mt5_p.account_info()
            if acc:
                result["balance"] = round(acc.balance, 2)
                result["equity"] = round(acc.equity, 2)
                result["margin"] = round(acc.margin, 2) if hasattr(acc, 'margin') else 0
            
            pos = mt5_p.positions_get(symbol=MT5_SYMBOL)
            if pos:
                p = pos[0]
                side = "BUY" if p.type == 0 else "SELL"
                result["has_position"] = True
                result["side"] = side
                result["volume"] = p.volume
                result["entry"] = p.price_open
                result["sl"] = p.sl if hasattr(p, 'sl') else 0
                result["tp"] = p.tp if hasattr(p, 'tp') else 0
                result["profit"] = round(p.profit, 2) if hasattr(p, 'profit') else 0
                result["ticket"] = p.ticket
            
            # 最近的K线 (用于画图)
            rates_15 = mt5_p.copy_rates_from_pos(MT5_SYMBOL, mt5_p.TIMEFRAME_M15, 0, 40)
            if rates_15 is not None and len(rates_15) > 0:
                klines = []
                for r in rates_15:
                    klines.append({
                        "time": datetime.datetime.fromtimestamp(r[0]).strftime("%H:%M"),
                        "open": round(r[1], 2), "high": round(r[2], 2),
                        "low": round(r[3], 2), "close": round(r[4], 2)
                    })
                result["klines_15m"] = klines
            
            mt5_p.shutdown()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/signal")
    def api_signal():
        refresh_data()
        sid = request.args.get("strategy", type=int)
        if sid is not None and 0 <= sid < len(strategies):
            s = strategies[sid]
            sig = s.on_data(bars_4h)
            return jsonify({
                "strategy": s.name,
                "signal": sig.signal,
                "text": "买入" if sig.signal == 1 else ("卖出" if sig.signal == -1 else "观望"),
                "data": {k: round(v, 2) for k, v in sig.data.items()},
                "price": bars_4h[-1].close if bars_4h else 0,
                "real_price": get_real_time_price(),
                "time": datetime.datetime.now().strftime("%H:%M:%S")
            })
        
        signals = []
        for i, s in enumerate(strategies):
            sig = s.on_data(bars_4h)
            signals.append({
                "id": i, "name": s.name, "signal": sig.signal,
                "text": "买入" if sig.signal == 1 else ("卖出" if sig.signal == -1 else "观望"),
                "data": {k: round(v, 2) for k, v in sig.data.items()}
            })
        return jsonify({
            "price": bars_4h[-1].close if bars_4h else 0,
            "real_price": get_real_time_price(),
            "signals": signals,
            "bars": len(bars_4h),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    
    # ----- 多周期共振 API -----
    @app.route("/api/resonance")
    def api_resonance():
        import MetaTrader5 as mt5_r
        try:
            mt5_r.initialize(path=MT5_PATH)
            mt5_r.symbol_select(MT5_SYMBOL, True)
            tf_map = [("5m",mt5_r.TIMEFRAME_M5),("15m",mt5_r.TIMEFRAME_M15),("30m",mt5_r.TIMEFRAME_M30),("1h",mt5_r.TIMEFRAME_H1),("4h",mt5_r.TIMEFRAME_H4)]
            results=[]
            for nm,tf in tf_map:
                rates=mt5_r.copy_rates_from_pos(MT5_SYMBOL,tf,0,60)
                if rates is None or len(rates)<30: continue
                cl=[r[4] for r in rates]
                e20=calc_ema(cl,20); rsi=calc_rsi(cl,14)
                p,e,r=cl[-1],e20[-1],rsi[-1]
                sig=1 if (p>e and 50<r<70) else (-1 if (p<e and 30<r<50) else 0)
                results.append({"timeframe":nm,"price":round(p,2),"ema20":round(e,2),"rsi":round(r,1),"signal":sig,"direction":"买入" if sig==1 else ("卖出" if sig==-1 else "观望")})
            mt5_r.shutdown()
            buys=sum(1 for x in results if x["signal"]==1)
            sells=sum(1 for x in results if x["signal"]==-1)
            waits=sum(1 for x in results if x["signal"]==0)
            total=len(results)
            c=0; ct="观望"
            if buys>=3: c=1; ct=f"看涨共振({buys}/{total})→建议做多"
            elif sells>=3: c=-1; ct=f"看跌共振({sells}/{total})→建议做空"
            elif buys>sells: c=1; ct=f"弱看涨({buys}/{total})"
            elif sells>buys: c=-1; ct=f"弱看跌({sells}/{total})"
            return jsonify({"results":results,"buys":buys,"sells":sells,"waits":waits,"total":total,"consensus":c,"consensus_text":ct,"real_price":get_real_time_price(),"time":datetime.datetime.now().strftime("%H:%M:%S")})
        except Exception as e:
            return jsonify({"error":str(e)}),500
    
    # ----- ML 预测 API -----
    @app.route("/api/predict")
    def api_predict():
        """用训练好的ML模型预测下一根1h K线走势"""
        try:
            import pickle, numpy as np
            import MetaTrader5 as mt5_m5
            
            model_path = "kline_model.pkl"
            if not os.path.exists(model_path):
                return jsonify({"error": "模型未训练, 先运行 train_kline_model.py"})
            
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)
            
            model = model_data["model"]
            window = 24
            
            # 从MT5获取最新的1h数据
            mt5_m5.initialize(path="C:/Program Files/MetaTrader 5/terminal64.exe")
            mt5_m5.symbol_select("BTCUSD", True)
            rates = mt5_m5.copy_rates_from_pos("BTCUSD", mt5_m5.TIMEFRAME_H1, 0, window + 5)
            mt5_m5.shutdown()
            
            if rates is None or len(rates) < window + 2:
                return jsonify({"error": f"1h数据不足({len(rates) if rates else 0})"})
            
            closes = [r[4] for r in rates]
            highs = [r[2] for r in rates]
            lows = [r[3] for r in rates]
            price = closes[-1]
            
            # 构造特征 (和训练时一致)
            feats = [
                1 if closes[-1] > closes[-2] else 0,
                1 if closes[-1] > closes[-window] else 0,
                (price - min(closes)) / (max(closes) - min(closes) + 0.01),
                (highs[-1] - lows[-1]) / price,
                np.std(closes[-6:]) / price,
                np.std(closes) / price,
            ]
            
            prob = model.predict_proba([feats])[0]
            pred = model.predict([feats])[0]
            
            direction = "涨(做多)" if pred == 1 else "跌(做空)"
            confidence = prob[pred]
            
            return jsonify({
                "prediction": int(pred),
                "direction": direction,
                "confidence": round(float(confidence), 4),
                "prob_up": round(float(prob[1]), 4),
                "prob_down": round(float(prob[0]), 4),
                "price": price,
                "model_stats": {
                    "test_acc": round(model_data["test_acc"], 4),
                    "trained_at": model_data["trained_at"],
                    "samples": model_data["samples"],
                }
            })
        except Exception as e:
            import traceback
            return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500
    
    @app.route("/api/backtest")
    def api_backtest():
        sid = request.args.get("strategy", type=int) or 0
        tf = request.args.get("tf", "4h")
        count = request.args.get("count", type=int) or 500
        capital = request.args.get("capital", type=float) or 10000.0
        
        if sid < 0 or sid >= len(strategies):
            return jsonify({"error": "策略ID无效"}), 400
        
        tf_map = {"1m": "1m", "5m": "5m", "1h": "1h", "4h": "4h", "1d": "1d"}
        if tf not in tf_map:
            return jsonify({"error": "周期无效"}), 400
        
        try:
            b = fetcher.fetch_bars(tf, count)
            if len(b) < 30:
                return jsonify({"error": f"数据不足({len(b)}根)"}), 400
            
            r = Backtester.run(b, strategies[sid], initial_capital=capital)
            
            # 生成图表并保存为base64
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            fig, axes = plt.subplots(2, 1, figsize=(12, 6),
                gridspec_kw={"height_ratios": [3, 1]})
            
            times = [ep.time for ep in r.equity_curve]
            eqs = [ep.equity for ep in r.equity_curve]
            dds = [ep.drawdown for ep in r.equity_curve]
            
            axes[0].plot(times, eqs, "#2196F3", lw=1.5)
            axes[0].axhline(capital, color="#999", ls="--", alpha=0.5)
            axes[0].fill_between(times, capital, eqs,
                where=[e>=capital for e in eqs], color="#4CAF50", alpha=0.15)
            axes[0].fill_between(times, capital, eqs,
                where=[e<capital for e in eqs], color="#F44336", alpha=0.1)
            axes[0].set_ylabel("净值 ($)")
            axes[0].grid(True, alpha=0.3)
            
            for t in r.trades:
                if t.exit_time:
                    axes[0].axvline(t.entry_time,
                        color="#4CAF50" if t.pnl>0 else "#F44336", alpha=0.08, lw=0.5)
            
            axes[1].fill_between(times, 0, dds, color="#F44336", alpha=0.3)
            axes[1].plot(times, dds, "#F44336", lw=1)
            axes[1].set_ylabel("回撤 (%)")
            axes[1].invert_yaxis()
            axes[1].grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            import io, base64
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            plt.close()
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode()
            
            trades_data = []
            for t in r.trades:
                if t.exit_time:
                    trades_data.append({
                        "side": t.side,
                        "entry": t.entry_time.strftime("%m/%d %H:00"),
                        "exit": t.exit_time.strftime("%m/%d %H:00"),
                        "pnl": round(t.pnl, 2),
                        "reason": t.exit_reason
                    })
            
            return jsonify({
                "strategy": strategies[sid].name,
                "tf": tf,
                "total_pnl": round(r.total_pnl, 2),
                "total_pnl_pct": round(r.total_pnl_pct, 2),
                "trades": r.total_trades,
                "win_rate": round(r.win_rate, 1),
                "max_dd": round(r.max_drawdown, 2),
                "avg_win": round(r.avg_win, 2),
                "avg_loss": round(r.avg_loss, 2),
                "profit_factor": round(r.profit_factor, 2),
                "sharpe": round(r.sharpe, 2),
                "chart": img_b64,
                "trades_list": trades_data[-20:],
                "capital": capital
            })
        except Exception as e:
            import traceback
            return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500
    
    # ======================== 页面 ========================
    
    INDEX_HTML = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>BTC 交易策略机器人</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,'Microsoft YaHei',sans-serif}
        body{background:#0d1117;color:#c9d1d9;padding:20px;max-width:1200px;margin:0 auto}
        .header{text-align:center;padding:20px 0;border-bottom:1px solid #30363d;margin-bottom:25px}
        .header h1{font-size:28px;background:linear-gradient(135deg,#58a6ff,#3fb950);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .header p{color:#8b949e;font-size:14px;margin-top:5px}
        .tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
        .tab{padding:10px 22px;border:1px solid #30363d;border-radius:8px;cursor:pointer;background:#161b22;color:#c9d1d9;font-size:14px;transition:all .2s}
        .tab.active{background:#1f6feb;border-color:#1f6feb;color:#fff}
        .tab:hover{background:#21262d}
        .panel{display:none;animation:fadeIn .3s}
        .panel.active{display:block}
        @keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:16px}
        .card h3{font-size:16px;color:#58a6ff;margin-bottom:12px}
        .price-box{text-align:center;padding:25px}
        .price{font-size:42px;font-weight:700;color:#f0f6fc}
        .price-change{font-size:18px;margin-top:5px}
        .up{color:#3fb950}
        .down{color:#f85149}
        .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
        .grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
        .stat-box{text-align:center;padding:15px}
        .stat-value{font-size:28px;font-weight:700;color:#f0f6fc}
        .stat-label{font-size:13px;color:#8b949e;margin-top:4px}
        select,input{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:8px 12px;border-radius:6px;font-size:14px;width:100%;margin-bottom:8px}
        select option{background:#161b22}
        .btn{background:#1f6feb;color:#fff;border:none;padding:10px 24px;border-radius:6px;cursor:pointer;font-size:14px;transition:all .2s}
        .btn:hover{background:#388bfd}
        .btn:disabled{opacity:.5;cursor:not-allowed}
        .signal-box{padding:15px;border-radius:8px;text-align:center;margin-bottom:12px}
        .signal-buy{background:rgba(63,185,80,0.15);border:1px solid #3fb950}
        .signal-sell{background:rgba(248,81,73,0.15);border:1px solid #f85149}
        .signal-wait{background:rgba(139,148,158,0.1);border:1px solid #30363d}
        .signal-icon{font-size:32px;margin-bottom:8px}
        .signal-text{font-size:20px;font-weight:700}
        .signal-price{font-size:13px;color:#8b949e;margin-top:4px}
        .chart-container{width:100%;text-align:center}
        .chart-container img{max-width:100%;border-radius:8px;margin-top:12px}
        .loading{text-align:center;padding:40px;color:#8b949e}
        .loading:after{content:'';display:inline-block;width:20px;height:20px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin .8s linear infinite;margin-left:8px;vertical-align:middle}
        @keyframes spin{to{transform:rotate(360deg)}}
        table{width:100%;border-collapse:collapse;font-size:13px}
        th{text-align:left;color:#8b949e;font-weight:400;padding:8px 6px;border-bottom:1px solid #30363d}
        td{padding:6px;border-bottom:1px solid #21262d}
        .green{color:#3fb950}
        .red{color:#f85149}
        .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
        .row label{font-size:13px;color:#8b949e;min-width:60px}
        @media(max-width:768px){.grid-2,.grid-3{grid-template-columns:1fr}}
    </style>
    </head>
    <body>
    <div class="header">
        <h1>🤖 BTC 交易策略机器人</h1>
        <p>实时信号 · 历史回测 · 全策略对比</p>
    </div>
    
    <div class="tabs">
        <div class="tab active" onclick="switchTab('dashboard')">📊 仪表盘</div>
        <div class="tab" onclick="switchTab('backtest')">🔙 回测</div>
        <div class="tab" onclick="switchTab('monitor')">📡 实时</div>
        <div class="tab" onclick="switchTab('compare')">📊 全策略对比</div>
        <div class="tab" onclick="switchTab('auto')">🤖 自动交易</div>
    </div>
    
    <!-- 仪表盘 -->
    <div id="panel-dashboard" class="panel active">
        <!-- 价格 -->
        <div class="card"><div id="price-display" class="price-box"><div class="price">$ --</div><div class="price-change">--</div></div></div>
        
        <!-- 持仓 + 账户 -->
        <div class="card"><h3>💰 MT5持仓 · 账户#60107268</h3>
            <div class="grid-2">
                <div><div class="stat-box"><div class="stat-value" id="pos-side">--</div><div class="stat-label">方向</div></div></div>
                <div><div class="stat-box"><div class="stat-value" id="pos-pnl" style="color:#3fb950">--</div><div class="stat-label">浮动盈亏</div></div></div>
            </div>
            <div class="grid-3" style="margin-top:8px">
                <div class="stat-box"><div class="stat-value" id="pos-entry">--</div><div class="stat-label">入场价</div></div>
                <div class="stat-box"><div class="stat-value" id="pos-sl">--</div><div class="stat-label">止损</div></div>
                <div class="stat-box"><div class="stat-value" id="acc-balance">--</div><div class="stat-label">余额</div></div>
            </div>
        </div>
        
        <!-- 15m K线 (迷你图) -->
        <div class="card"><h3>📈 BTCUSD 15m</h3><canvas id="kline-chart" height="180"></canvas></div>
        
        <!-- 多周期共振 + 策略信号 -->
        <div class="grid-2">
            <div class="card"><h3>📡 多周期共振</h3><div id="resonance-bar" style="margin-bottom:8px;font-size:15px;font-weight:700">--</div><div id="resonance-grid" style="font-size:12px">--</div></div>
            <div class="card"><h3>🧠 AI预测</h3><div id="ml-status-card" style="text-align:center;font-size:14px">--</div></div>
        </div>
        <div id="dashboard-signals"></div>
    </div>
    
    <!-- 回测 -->
    <div id="panel-backtest" class="panel">
        <div class="card">
            <h3>🔧 回测设置</h3>
            <div class="row">
                <label>策略:</label>
                <select id="bt-strategy" style="width:auto;flex:1">{% for s in strategies %}
                    <option value="{{ loop.index0 }}">{{ s.name }}</option>{% endfor %}
                </select>
                <label>周期:</label>
                <select id="bt-tf" style="width:auto;flex:0.5">
                    <option value="1m">1分钟</option><option value="5m">5分钟</option>
                    <option value="1h" selected>1小时</option><option value="4h">4小时</option>
                    <option value="1d">日线</option>
                </select>
                <label>K线:</label>
                <select id="bt-count" style="width:auto;flex:0.5">
                    <option value="200">200</option><option value="500" selected>500</option>
                    <option value="1000">1000</option>
                </select>
                <label>资金:</label>
                <select id="bt-capital" style="width:auto;flex:0.5">
                    <option value="500">$500</option><option value="2000">$2,000</option>
                    <option value="10000" selected>$10,000</option>
                </select>
                <button class="btn" onclick="runBacktest()">🚀 开始回测</button>
            </div>
        </div>
        <div id="bt-result"></div>
    </div>
    
    <!-- 实时监控 -->
    <div id="panel-monitor" class="panel">
        <div class="card">
            <div class="row">
                <h3 style="margin:0">📡 实时信号</h3>
                <span id="mon-update-time" style="color:#8b949e;font-size:13px"></span>
            </div>
        </div>
        <div id="mon-signals"></div>
    </div>
    
    <!-- 全策略对比 -->
    <div id="panel-compare" class="panel">
        <div class="card">
            <h3>⚡ 全策略对比</h3>
            <div class="row">
                <label>周期:</label>
                <select id="cp-tf" style="width:auto;flex:0.5">
                    <option value="1m">1分钟</option><option value="5m">5分钟</option>
                    <option value="1h" selected>1小时</option><option value="4h">4小时</option>
                    <option value="1d">日线</option>
                </select>
                <label>K线:</label>
                <select id="cp-count" style="width:auto;flex:0.5">
                    <option value="200">200</option><option value="500" selected>500</option>
                    <option value="1000">1000</option>
                </select>
                <button class="btn" onclick="runCompare()">🚀 开始对比</button>
            </div>
        </div>
        <div id="cp-result"></div>
    </div>
    
    <!-- 自动交易 -->
    <div id="panel-auto" class="panel">
        <div class="card">
            <h3>🤖 MT5 自动交易</h3>
            <div class="row" style="gap:12px;margin-bottom:12px">
                <button class="btn" id="auto-start-btn" onclick="autoStart()">▶ 启动自动交易</button>
                <button class="btn" style="background:#f85149" onclick="autoStop()">⏹ 停止</button>
                <button class="btn" style="background:#30363d" onclick="autoRefresh()">🔄 刷新</button>
            </div>
            <div style="font-size:14px;margin-bottom:8px">
                <span id="auto-status" style="color:#8b949e">检查中...</span>
            </div>
            <div style="font-size:13px;color:#8b949e;margin-bottom:8px">
                策略: RSI+EMA 日线 | 账户 #60107268 | 风险$10/笔 | SL=1.5×ATR
            </div>
            <div id="auto-logs" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;max-height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.6"></div>
        </div>
    </div>
    
    <script>
    function switchTab(name){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));event.currentTarget.classList.add('active');document.getElementById('panel-'+name).classList.add('active')}
    
    // 仪表盘
    async function loadDashboard(){try{
        let r=await fetch('/api/signal'),d=await r.json();
        let p=d.real_price||d.price||0;
        document.querySelector('#price-display .price').textContent='$ '+p.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
        document.querySelector('#price-display .price-change').textContent='MT5实时Bid | 每10秒刷新';

        // 策略信号
        let h=document.getElementById('dashboard-signals');
        h.innerHTML='<div class="grid-3">'+d.signals.map(s=>{
            let cls=s.signal==1?'signal-buy':s.signal==-1?'signal-sell':'signal-wait';
            let icon=s.signal==1?'🟢':s.signal==-1?'🔴':'⚪';
            let txt=s.signal==1?'买入':s.signal==-1?'卖出':'观望';
            return `<div class=\"signal-box ${cls}\"><div class=\"signal-icon\">${icon}</div><div class=\"signal-text\">${txt}</div><div style=\"font-size:12px;color:#8b949e;margin-top:4px\">${s.name}</div></div>`
        }).join('')+'</div>';

        // MT5持仓
        try{
            let pr=await fetch('/api/position'),pd=await pr.json();
            document.getElementById('acc-balance').textContent='$'+pd.balance.toFixed(0);
            if(pd.has_position){
                let cls=pd.side=='BUY'?'#3fb950':'#f85149';
                let pnlCls=pd.profit>=0?'#3fb950':'#f85149';
                document.getElementById('pos-side').innerHTML=`<span style=\"color:${cls};font-size:24px\">${pd.side=='BUY'?'🟢 做多':'🔴 做空'}</span>`;
                document.getElementById('pos-pnl').style.color=pnlCls;
                document.getElementById('pos-pnl').textContent=(pd.profit>=0?'+':'')+'$'+pd.profit.toFixed(2);
                document.getElementById('pos-entry').textContent='$'+pd.entry.toFixed(0);
                document.getElementById('pos-sl').textContent='$'+pd.sl.toFixed(0);
            }else{
                document.getElementById('pos-side').innerHTML='<span style=\"color:#8b949e;font-size:24px\">⚪ 空仓</span>';
                document.getElementById('pos-pnl').textContent='--';
                document.getElementById('pos-entry').textContent='--';
                document.getElementById('pos-sl').textContent='--';
            }
            // 画K线
            if(pd.klines_15m){
                drawKLine('kline-chart', pd.klines_15m);
            }
        }catch(e){}

        // 共振
        try{
            let rr=await fetch('/api/resonance'),rd=await rr.json();
            let bar=document.getElementById('resonance-bar');
            if(rd.consensus==1) bar.innerHTML='<span style=\"color:#3fb950\">✅ '+rd.consensus_text+'</span>';
            else if(rd.consensus==-1) bar.innerHTML='<span style=\"color:#f85149\">✅ '+rd.consensus_text+'</span>';
            else bar.innerHTML='<span style=\"color:#8b949e\">⚪ '+rd.consensus_text+'</span>';
            document.getElementById('resonance-grid').innerHTML=rd.results.map(r=>{
                let s=r.signal==1?'🟢买':r.signal==-1?'🔴卖':'⚪';
                return `<div style=\"background:#0d1117;border-radius:4px;padding:6px;text-align:center;border:1px solid #30363d;margin-bottom:4px\"><b>${s}</b> ${r.timeframe} RSI=${r.rsi}</div>`
            }).join('');
        }catch(e){}

        // ML
        try{
            let mr=await fetch('/api/predict'),md=await mr.json();
            if(md.prediction!==undefined){
                let dir=md.prediction==1?'🟢 涨(做多)':'🔴 跌(做空)';
                document.getElementById('ml-status-card').innerHTML=`<div style=\"font-size:18px;font-weight:700\">${dir}</div><div style=\"margin-top:6px\">涨${(md.prob_up*100).toFixed(0)}% 跌${(md.prob_down*100).toFixed(0)}%</div><div style=\"color:#8b949e;font-size:11px;margin-top:4px\">置信度: ${(md.confidence*100).toFixed(0)}%</div>`;
            }
        }catch(e){}
    }catch(e){}}

    var klineChart=null;
    function drawKLine(canvasId, data){
        var ctx=document.getElementById(canvasId).getContext('2d');
        if(klineChart){klineChart.destroy();}
        klineChart=new Chart(ctx,{
            type:'line',
            data:{labels:data.map(d=>d.time),datasets:[{label:'Close',data:data.map(d=>d.close),borderColor:'#58a6ff',borderWidth:1.5,pointRadius:0,tension:0}]},
            options:{
                responsive:true,maintainAspectRatio:false,
                plugins:{legend:{display:false}},
                scales:{
                    x:{ticks:{color:'#8b949e',maxTicksLimit:8},grid:{color:'#21262d'}},
                    y:{ticks:{color:'#8b949e',callback:v=>'$'+v.toFixed(0)},grid:{color:'#21262d'}}
                },
                interaction:{intersect:false,mode:'index'}
            }
        });
    }
    
    // 回测
    async function runBacktest(){
        let sid=document.getElementById('bt-strategy').value;
        let tf=document.getElementById('bt-tf').value;
        let cnt=document.getElementById('bt-count').value;
        let cap=document.getElementById('bt-capital').value;
        let btn=event.currentTarget;btn.disabled=true;btn.textContent='⏳ 回测中...';
        document.getElementById('bt-result').innerHTML='<div class="loading">正在获取数据并跑回测...</div>';
        try{
            let r=await fetch(`/api/backtest?strategy=${sid}&tf=${tf}&count=${cnt}&capital=${cap}`);
            let d=await r.json();
            if(d.error){document.getElementById('bt-result').innerHTML='<div class="card" style="color:#f85149">❌ '+d.error+'</div>';return}
            let img=d.chart?'<img src="data:image/png;base64,'+d.chart+'">':'';
            let pnlCls=d.total_pnl>=0?'green':'red';
            let tradesHtml='';
            if(d.trades_list&&d.trades_list.length){tradesHtml='<table><tr><th>方向</th><th>入场</th><th>出场</th><th>盈亏</th><th>原因</th></tr>'+d.trades_list.map(t=>'<tr><td>'+(t.side=='BUY'?'🟢买':'🔴卖')+'</td><td>'+t.entry+'</td><td>'+t.exit+'</td><td class="'+(t.pnl>=0?'green':'red')+'">$'+t.pnl.toFixed(2)+'</td><td>'+t.reason+'</td></tr>').join('')+'</table>'}
            document.getElementById('bt-result').innerHTML=
                '<div class="card"><h3>📊 '+d.strategy+'  |  '+d.tf+'  |  '+(d.capital?('$'+Number(d.capital).toLocaleString()):'')+'</h3>'+
                '<div class="grid-3"><div class="stat-box"><div class="stat-value '+pnlCls+'">$'+d.total_pnl.toFixed(2)+'</div><div class="stat-label">净盈亏 ('+d.total_pnl_pct+'%)</div></div>'+
                '<div class="stat-box"><div class="stat-value">'+d.trades+'</div><div class="stat-label">交易次数</div></div>'+
                '<div class="stat-box"><div class="stat-value">'+d.win_rate+'%</div><div class="stat-label">胜率</div></div></div>'+
                '<div class="grid-3" style="margin-top:8px"><div class="stat-box"><div class="stat-value">'+d.max_dd+'%</div><div class="stat-label">最大回撤</div></div>'+
                '<div class="stat-box"><div class="stat-value">'+d.profit_factor+'</div><div class="stat-label">盈亏比</div></div>'+
                '<div class="stat-box"><div class="stat-value">'+d.sharpe+'</div><div class="stat-label">夏普率</div></div></div>'+
                '<div class="chart-container">'+img+'</div>'+
                (tradesHtml?'<div style="margin-top:12px;max-height:300px;overflow-y:auto">'+tradesHtml+'</div>':'')+'</div>'
        }catch(e){document.getElementById('bt-result').innerHTML='<div class="card" style="color:#f85149">❌ 请求失败: '+e.message+'</div>'}
        btn.disabled=false;btn.textContent='🚀 开始回测'
    }
    
    // 实时监控
    async function loadMonitor(){try{
        let r=await fetch('/api/signal'),d=await r.json();
        let rp=d.real_price||d.price||0;
        document.getElementById('mon-update-time').textContent='实时BTC: $'+rp.toLocaleString(undefined,{minimumFractionDigits:2})+'  |  4h收盘: $'+(d.price||0).toLocaleString(undefined,{minimumFractionDigits:2})+'  |  '+d.time;
        let h=document.getElementById('mon-signals');
        h.innerHTML='<div class="grid-3">'+d.signals.map((s,i)=>{
            let cls=s.signal==1?'signal-buy':s.signal==-1?'signal-sell':'signal-wait';
            let icon=s.signal==1?'🟢':s.signal==-1?'🔴':'⚪';
            let txt=s.signal==1?'买入':s.signal==-1?'卖出':'观望';
            let data=Object.entries(s.data).map(([k,v])=>k+'='+v).join(' | ');
            return '<div class="signal-box '+cls+'"><div class="signal-icon">'+icon+'</div><div class="signal-text">'+txt+'</div><div style="font-size:13px;color:#8b949e;margin-top:6px">'+s.name+'</div><div style="font-size:12px;color:#8b949e;margin-top:4px">'+data+'</div></div>'
        }).join('')+'</div>'
    }catch(e){}setTimeout(loadMonitor,5000)}
    
    // 全策略对比
    async function runCompare(){
        let tf=document.getElementById('cp-tf').value;
        let cnt=document.getElementById('cp-count').value;
        let btn=event.currentTarget;btn.disabled=true;btn.textContent='⏳ 对比中...';
        document.getElementById('cp-result').innerHTML='<div class="loading">正在运行全策略对比...</div>';
        try{
            let results=[];
            {% for s in strategies %}
            let r{{ loop.index0 }} = await fetch('/api/backtest?strategy={{ loop.index0 }}&tf='+tf+'&count='+cnt+'&capital=10000');
            results.push(r{{ loop.index0 }}.ok ? await r{{ loop.index0 }}.json() : {total_pnl:-99999,strategy:'{{ strategies[loop.index0].name }}',error:'请求失败'});
            {% endfor %}
            let valid = results.filter(r => r && !r.error);
            if(valid.length===0){
                document.getElementById('cp-result').innerHTML='<div class="card" style="color:#f85149">❌ 所有策略回测均失败，检查数据或重试</div>';
                btn.disabled=false;btn.textContent='🚀 开始对比';return;
            }
            valid.sort((a,b)=>b.total_pnl-a.total_pnl);
            let rows=valid.map((d,i)=>{
                let rank=i==0?'🏆':i==1?'🥈':i==2?'🥉':'#'+(i+1);
                let cls=d.total_pnl>=0?'green':'red';
                return '<tr><td>'+rank+'</td><td>'+d.strategy+'</td><td class="'+cls+'">$'+d.total_pnl.toFixed(2)+' ('+(d.total_pnl_pct||0)+'%)</td><td>'+d.win_rate+'%</td><td>'+d.max_dd+'%</td><td>'+d.trades+'</td><td>'+(d.profit_factor||0).toFixed(2)+'</td></tr>'
            }).join('');
            document.getElementById('cp-result').innerHTML=
                '<div class="card"><h3>📊 全策略排名</h3><table><tr><th>排名</th><th>策略</th><th>净盈亏</th><th>胜率</th><th>回撤</th><th>交易</th><th>盈亏比</th></tr>'+rows+'</table></div>'+
                (valid[0]?'<div class="card"><h3>🏆 冠军: '+valid[0].strategy+'</h3><div class="chart-container"><img src="data:image/png;base64,'+valid[0].chart+'"></div></div>':'')
        }catch(e){document.getElementById('cp-result').innerHTML='<div class="card" style="color:#f85149">❌ 请求失败: '+e.message+'</div>'}
        btn.disabled=false;btn.textContent='🚀 开始对比'
    }
    
    // 自动交易
    async function autoRefresh(){
        try{
            let r=await fetch('/api/auto_trade'),d=await r.json();
            let st=d.enabled?'🟢 运行中':'⚪ 已停止';
            document.getElementById('auto-status').innerHTML=st+' | '+d.status;
            let logs=d.logs||[];
            document.getElementById('auto-logs').innerHTML=logs.map(l=>'<div>'+l+'</div>').join('')||'<div style="color:#8b949e">暂无记录</div>';
        }catch(e){}
    }
    async function autoStart(){
        await fetch('/api/auto_trade?cmd=start');
        document.getElementById('auto-start-btn').disabled=true;
        document.getElementById('auto-start-btn').textContent='▶ 已在运行';
        setTimeout(autoRefresh,2000);
    }
    async function autoStop(){
        await fetch('/api/auto_trade?cmd=stop');
        document.getElementById('auto-start-btn').disabled=false;
        document.getElementById('auto-start-btn').textContent='▶ 启动自动交易';
        setTimeout(autoRefresh,2000);
    }
    
    loadDashboard();
    setInterval(loadDashboard,10000);
    setTimeout(loadMonitor,500);
    setTimeout(autoRefresh,1000);
    setInterval(autoRefresh,5000);
    </script>
    </body>
    </html>
    """
    
    @app.route("/")
    def index():
        return render_template_string(INDEX_HTML, strategies=strategies)
    
    # 用默认端口，加一个简单的页面打开
    port = 5050  # 避免和MT5的端口5000冲突
    print(f"\n{'='*55}")
    print(f"  🌐 BTC 操作面板")
    print(f"  http://127.0.0.1:{port}")
    print(f"{'='*55}")
    print(f"  📋 功能:")
    print(f"    1. 仪表盘 — 实时价格 + 策略信号")
    print(f"    2. 回测 — 选策略/周期→跑→看图")
    print(f"    3. 实时 — 自动刷新策略信号")
    print(f"    4. 全策略对比 — 一键排名")
    print(f"    5. 自动交易 — MT5模拟盘 #60107268 (需手动启动)")
    print(f"{'='*55}\n")
    
    app.run(host="127.0.0.1", port=port, debug=False)


# ======================================================================
#  10. 程序入口
# ======================================================================

if __name__ == "__main__":
    import sys
    
    # 命令行模式: --server 启动API服务器
    if "--server" in sys.argv:
        run_api_server()
    else:
        try:
            main_menu()
        except KeyboardInterrupt:
            print("\n\n  👋 退出")
        except Exception as e:
            print(f"\n  ❌ 错误: {e}")
            import traceback
            traceback.print_exc()
