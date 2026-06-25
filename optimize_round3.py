#!/usr/bin/env python3
# Round 3: Optimization
import sys, os, json, numpy as np, matplotlib, urllib.request
matplotlib.use("Agg")
sys.path.insert(0, "C:/Users/82682/Desktop")
os.chdir("C:/Users/82682/Desktop")
from btc_trader import *

fetcher = DataFetcher()
strategies = get_all_strategies()
bars_1d = fetcher.fetch_bars("1d", 400)
bars_4h = fetcher.fetch_bars("4h", 2200)

print("=" * 55)
print("  A: RSI+EMA 1d Optimization")
print("=" * 55)
combos = []
for risk in [25, 50, 100]:
    for sl in [1.5, 2.0, 3.0, 4.0]:
        for tt, tb in [(100,40), (200,80), (300,120), (500,200), (9999,1)]:
            r = Backtester.run(bars_1d, strategies[3], risk_per_trade=risk, trail_trigger=tt, trail_back=tb, sl_atr=sl)
            net = r.total_pnl - r.total_trades * 2.0
            combos.append((risk, sl, tt, tb, r, net))
combos.sort(key=lambda x: x[5], reverse=True)
for rank, (risk, sl, tt, tb, r, net) in enumerate(combos[:10]):
    lbl = "no-trail" if tt >= 9999 else f"T{tt}/{tb}"
    print(f"  #{rank+1} Risk${risk} SL{sl}x {lbl}: ${r.total_pnl:.2f} net=${net:.2f} {r.total_trades}trades WR{r.win_rate:.0f}% DD{r.max_drawdown:.1f}%")

print("=" * 55)
print("  B: Combo Signal (2+/4)")
print("=" * 55)
class ComboStrategy(BaseStrategy):
    name = "Combo(2+/4)"
    def __init__(self, sub_strategies):
        super().__init__()
        self.subs = sub_strategies
    def on_data(self, bars):
        r = StrategyResult()
        signals = [s.on_data(bars).signal for s in self.subs]
        bc = sum(1 for x in signals if x == 1)
        sc = sum(1 for x in signals if x == -1)
        if bc >= 2: r.signal = 1
        elif sc >= 2: r.signal = -1
        r.data = {"buy": bc, "sell": sc}
        return r

combo = ComboStrategy(strategies)
for tf, bars, tt, tb, sl in [("4h", bars_4h, 60, 25, 1.5), ("1d", bars_1d, 200, 80, 2.0), ("1d", bars_1d, 500, 200, 3.0)]:
    r = Backtester.run(bars, combo, risk_per_trade=50, trail_trigger=tt, trail_back=tb, sl_atr=sl)
    net = r.total_pnl - r.total_trades * 2.0
    print(f"  {tf} SL{sl}x T{tt}/{tb}: ${r.total_pnl:.2f} net=${net:.2f} {r.total_trades}t WR{r.win_rate:.0f}% DD{r.max_drawdown:.1f}%")

print("=" * 55)
print("  C: H4EMA20 Wide Stops")
print("=" * 55)
for sl in [2.0, 3.0, 4.0]:
    for tt, tb in [(200, 80), (300, 120), (500, 200)]:
        r = Backtester.run(bars_4h, strategies[0], risk_per_trade=50, trail_trigger=tt, trail_back=tb, sl_atr=sl)
        net = r.total_pnl - r.total_trades * 2.0
        print(f"  SL{sl}x T{tt}/{tb}: ${r.total_pnl:.2f} net=${net:.2f} {r.total_trades}t WR{r.win_rate:.0f}% DD{r.max_drawdown:.1f}%")

print("=" * 55)
print("  D: DailyMeanRev with bigger parameters")
print("=" * 55)
for risk in [50, 100, 200]:
    for sl in [2.0, 3.0]:
        for tt, tb in [(500, 200), (9999, 1)]:
            r = Backtester.run(bars_1d, strategies[2], risk_per_trade=risk, trail_trigger=tt, trail_back=tb, sl_atr=sl)
            net = r.total_pnl - r.total_trades * 2.0
            lbl = "no-trail" if tt >= 9999 else f"T{tt}/{tb}"
            print(f"  Risk${risk} SL{sl}x {lbl}: ${r.total_pnl:.2f} net=${net:.2f} {r.total_trades}t WR{r.win_rate:.0f}% DD{r.max_drawdown:.1f}%")

print("\nDone.")
