#!/usr/bin/env python3
"""6策略投票系统测试 — 4+/6 多数决"""
import sys, os, numpy as np
sys.path.insert(0, "D:/BTC")
os.chdir("D:/BTC")
from btc_trader import *

# ============================================================
# 新增2个策略
# ============================================================

# --- 策略5: MACD 交叉 ---
class MACDCross(BaseStrategy):
    name = "MACD 交叉"
    
    def on_data(self, bars):
        r = StrategyResult()
        closes = [b.close for b in bars]
        if len(closes) < 35:
            return r
        
        # 计算MACD
        ema12 = calc_ema(closes, 12)
        ema26 = calc_ema(closes, 26)
        macd = [ema12[i] - ema26[i] for i in range(len(closes))]
        signal = calc_ema(macd, 9)
        
        # MACD > 信号线 = 多头, MACD < 信号线 = 空头
        macd_v = macd[-1]
        sig_v = signal[-1]
        macd_p = macd[-2]
        sig_p = signal[-2]
        
        # 金叉死叉 + 趋势确认
        hist = macd_v - sig_v
        hist_p = macd_p - sig_p
        
        # 趋势: MACD在零轴上方为多头, 下方为空头
        trend_bull = macd_v > 0
        trend_bear = macd_v < 0
        
        if trend_bull and hist > 0:
            r.signal = 1
        elif trend_bear and hist < 0:
            r.signal = -1
        
        r.data = {"macd": round(macd_v, 0), "signal": round(sig_v, 0), "hist": round(hist, 0)}
        return r


# --- 策略6: SuperTrend ---
class SuperTrend(BaseStrategy):
    name = "SuperTrend"
    
    def on_data(self, bars):
        r = StrategyResult()
        if len(bars) < 15:
            return r
        
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]
        
        atr = calc_atr(highs, lows, closes, 10)
        period = 10
        multiplier = 3.0
        
        # 计算上下轨
        n = len(closes)
        upper = [0.0] * n
        lower = [0.0] * n
        trend = [1] * n  # 1=多头, -1=空头
        
        for i in range(period, n):
            mid = (highs[i] + lows[i]) / 2
            upper[i] = mid + multiplier * atr[i]
            lower[i] = mid - multiplier * atr[i]
            
            if i > period:
                if closes[i] > upper[i-1]:
                    trend[i] = 1
                elif closes[i] < lower[i-1]:
                    trend[i] = -1
                else:
                    trend[i] = trend[i-1]
                    
                if trend[i] == 1 and lower[i] < lower[i-1]:
                    lower[i] = lower[i-1]
                if trend[i] == -1 and upper[i] > upper[i-1]:
                    upper[i] = upper[i-1]
        
        r.signal = trend[-1]
        r.data = {"trend": "多头" if trend[-1]==1 else "空头", 
                  "upper": round(upper[-1], 0), "lower": round(lower[-1], 0)}
        return r


# ============================================================
# 投票策略 (N+/M 多数决)
# ============================================================
class VoteStrategy(BaseStrategy):
    """多数表决: 当 vote_threshold 个以上的策略同时同向时入场"""
    
    def __init__(self, sub_strategies, vote_threshold=4):
        super().__init__()
        self.subs = sub_strategies
        self.threshold = vote_threshold
        self.name = f"投票({vote_threshold}/{len(sub_strategies)})"
    
    def on_data(self, bars):
        r = StrategyResult()
        votes = []
        for s in self.subs:
            sig = s.on_data(bars)
            votes.append(sig.signal)
        
        buy_votes = sum(1 for v in votes if v == 1)
        sell_votes = sum(1 for v in votes if v == -1)
        
        if buy_votes >= self.threshold:
            r.signal = 1
        elif sell_votes >= self.threshold:
            r.signal = -1
        else:
            r.signal = 0
        
        r.data = {
            "buy": buy_votes,
            "sell": sell_votes,
            "total": len(self.subs)
        }
        return r


# ============================================================
# 测试
# ============================================================
print("=" * 55)
print("  BTC 6策略投票系统")
print("=" * 55)

fetcher = DataFetcher()
bars_1d = fetcher.fetch_bars("1d", 400)

# 6个策略
all_6 = get_all_strategies() + [MACDCross(), SuperTrend()]

print(f"\n{'='*55}")
print(f"  6个策略各自独立回测 (日线, 无追踪止盈)")
print(f"  参数: Risk$200, SL=1.5xATR, 策略反转出场")
print("="*55)

results_6 = []
for i, s in enumerate(all_6):
    r = Backtester.run(bars_1d, s, risk_per_trade=200,
                       trail_trigger=9999, trail_back=1, sl_atr=1.5)
    net = r.total_pnl - r.total_trades * 2.0
    results_6.append((i, s, r, net))

# 按净利排序
results_6.sort(key=lambda x: x[3], reverse=True)

print(f"\n  {'排名':>4s} {'策略':25s} {'净盈亏':>10s} {'去佣':>8s} {'交易':>6s} {'胜率':>5s} {'回撤':>5s}")
print("  " + "-"*72)
for rank, (idx, s, r, net) in enumerate(results_6):
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    medal = "🏆" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1:2d}"
    print(f"  {medal} {s.name:25s} {pnl_s:>10s} {net_s:>8s} {r.total_trades:5d} {r.win_rate:5.1f}% {r.max_drawdown:5.1f}%")


# ============================================================
# 投票策略 — 不同阈值
# ============================================================
print(f"\n{'='*55}")
print("  投票策略 — 不同阈值对比")
print("="*55)

for threshold in [3, 4, 5]:
    vote = VoteStrategy(all_6, threshold)
    r = Backtester.run(bars_1d, vote, risk_per_trade=200,
                       trail_trigger=9999, trail_back=1, sl_atr=1.5)
    net = r.total_pnl - r.total_trades * 2.0
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    print(f"  {threshold}/{len(all_6)} 多数决: {pnl_s:>10s} 去佣{net_s:>8s}  {r.total_trades:3d}笔 胜率{r.win_rate:5.1f}% 回撤{r.max_drawdown:5.1f}%")

# 尝试4+/6 + 不同止损参数
print(f"\n{'='*55}")
print("  4+/6 投票 + 不同止损参数")
print("="*55)
vote = VoteStrategy(all_6, 4)
for sl in [1.5, 2.0, 3.0]:
    r = Backtester.run(bars_1d, vote, risk_per_trade=200,
                       trail_trigger=9999, trail_back=1, sl_atr=sl)
    net = r.total_pnl - r.total_trades * 2.0
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    print(f"  SL={sl:.1f}x: {pnl_s:>10s} 去佣{net_s:>8s}  {r.total_trades:3d}笔 胜率{r.win_rate:5.1f}% 回撤{r.max_drawdown:5.1f}% 盈亏比{r.profit_factor:.2f}")


# ============================================================
# 3+/6 投票 + 适当止损 (更多交易)
# ============================================================
print(f"\n{'='*55}")
print("  3+/6 投票 (更激进的多数决)")
print("="*55)
vote3 = VoteStrategy(all_6, 3)
for sl in [1.5, 2.0, 3.0]:
    r = Backtester.run(bars_1d, vote3, risk_per_trade=200,
                       trail_trigger=9999, trail_back=1, sl_atr=sl)
    net = r.total_pnl - r.total_trades * 2.0
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    print(f"  SL={sl:.1f}x: {pnl_s:>10s} 去佣{net_s:>8s}  {r.total_trades:3d}笔 胜率{r.win_rate:5.1f}% 回撤{r.max_drawdown:5.1f}% 盈亏比{r.profit_factor:.2f}")


# ============================================================
# 总结
# ============================================================
print(f"\n{'='*55}")
print("  💡 结论")
print("="*55)

# 找到4+/6 投票 SL=1.5x的结果
vote_best = Backtester.run(bars_1d, VoteStrategy(all_6, 4), risk_per_trade=200,
                           trail_trigger=9999, trail_back=1, sl_atr=1.5)
net_best = vote_best.total_pnl - len(vote_best.trades) * 2.0  # 注意: trades是list不是int

# 找到最佳单策略 (RSI+EMA原版)
r_rsi = Backtester.run(bars_1d, get_all_strategies()[3], risk_per_trade=200,
                        trail_trigger=9999, trail_back=1, sl_atr=1.5)
net_rsi = r_rsi.total_pnl - len(r_rsi.trades) * 2.0

print(f"""
单策略最佳 (RSI+EMA):      +${r_rsi.total_pnl:.2f} 去佣+${net_rsi:.2f}  ({r_rsi.total_trades}笔)
4+/6 投票:                +${vote_best.total_pnl:.2f} 去佣+${net_best:.2f}  ({vote_best.total_trades}笔)

{'⭐ 投票系统更好!' if net_best > net_rsi else '📌 单策略更好'}
""")

# 过滤投票: 只用正期望策略
print(f"\n{'='*55}")
print("  过滤投票: 只用正期望策略 (RSI+EMA + H4EMA20 + SuperTrend)")
print("="*55)
good_ones = [get_all_strategies()[3], get_all_strategies()[0], all_6[5]]  # RSI, H4EMA20, SuperTrend
for th in [2, 3]:
    if th > len(good_ones): continue
    r = Backtester.run(bars_1d, VoteStrategy(good_ones, th), risk_per_trade=200,
                       trail_trigger=9999, trail_back=1, sl_atr=1.5)
    net = r.total_pnl - len(r.trades) * 2.0
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    print(f"  {th}/{len(good_ones)} 多数决: {pnl_s:>10s} 去佣{net_s:>8s}  {len(r.trades):3d}笔 胜率{r.win_rate:5.1f}% 回撤{r.max_drawdown:5.1f}%")

print(f"\n{'='*55}")
print("  💡 结论")
print("="*55)

# 生成对比图
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
fig.patch.set_facecolor("#0d1117")
for ax in axes:
    ax.set_facecolor("#161b22")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#30363d")
    ax.spines["bottom"].set_color("#30363d")
    ax.tick_params(colors="#8b949e")
    ax.yaxis.label.set_color("#c9d1d9")
    ax.title.set_color("#f0f6fc")

# 图1: 6个策略对比
colors = ["#58a6ff","#FF9800","#3fb950","#f85149","#C084FC","#38BDF8"]
ax = axes[0]
for idx, s in enumerate(all_6):
    r = Backtester.run(bars_1d, s, risk_per_trade=200, trail_trigger=9999, trail_back=1, sl_atr=1.5)
    times = [ep.time for ep in r.equity_curve]
    eqs = [ep.equity for ep in r.equity_curve]
    ax.plot(times, eqs, colors[idx % len(colors)], lw=1, alpha=0.8,
            label=f"{s.name[:12]}(${r.total_pnl:.0f})")
ax.axhline(10000, color="#30363d", ls="--", alpha=0.5)
ax.legend(fontsize=8, loc="upper left", facecolor="#161b22", labelcolor="#c9d1d9")
ax.set_title("6个独立策略对比 (日线, Risk$200, 无追踪)", fontsize=12, color="#f0f6fc")
ax.grid(True, alpha=0.1, color="#30363d")

# 图2: 投票策略
ax = axes[1]
for th, color, ls in [(3, "#58a6ff", "-"), (4, "#3fb950", "-"), (5, "#FF9800", "-")]:
    r = Backtester.run(bars_1d, VoteStrategy(all_6, th), risk_per_trade=200, trail_trigger=9999, trail_back=1, sl_atr=1.5)
    times = [ep.time for ep in r.equity_curve]
    eqs = [ep.equity for ep in r.equity_curve]
    ax.plot(times, eqs, color, lw=1.5, ls=ls,
            label=f"{th}/{len(all_6)} 投票 (${r.total_pnl:.0f}, {r.total_trades}笔)")
ax.axhline(10000, color="#30363d", ls="--", alpha=0.5)
ax.legend(fontsize=9, loc="upper left", facecolor="#161b22", labelcolor="#c9d1d9")
ax.set_title("投票策略对比 (不同阈值)", fontsize=12, color="#f0f6fc")
ax.grid(True, alpha=0.1, color="#30363d")

# 图3: 最佳投票 vs 最佳单策略
ax = axes[2]
r_best_vote = Backtester.run(bars_1d, VoteStrategy(all_6, 4), risk_per_trade=200, trail_trigger=9999, trail_back=1, sl_atr=1.5)
r_best_single = Backtester.run(bars_1d, get_all_strategies()[3], risk_per_trade=200, trail_trigger=9999, trail_back=1, sl_atr=1.5)

t_v = [ep.time for ep in r_best_vote.equity_curve]
e_v = [ep.equity for ep in r_best_vote.equity_curve]
t_s = [ep.time for ep in r_best_single.equity_curve]
e_s = [ep.equity for ep in r_best_single.equity_curve]

ax.plot(t_v, e_v, "#3fb950", lw=2, label=f"4/6投票 (${r_best_vote.total_pnl:.0f})")
ax.plot(t_s, e_s, "#58a6ff", lw=1.5, alpha=0.7, label=f"RSI+EMA (${r_best_single.total_pnl:.0f})")
ax.axhline(10000, color="#30363d", ls="--", alpha=0.5)
ax.legend(fontsize=9, loc="upper left", facecolor="#161b22", labelcolor="#c9d1d9")
ax.set_title(f"投票 vs 单策略 — 最终对比", fontsize=12, color="#f0f6fc")
ax.set_xlabel("时间", fontsize=10, color="#c9d1d9")
ax.grid(True, alpha=0.1, color="#30363d")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

plt.tight_layout()
plt.savefig("vote_system_report.png", dpi=150, bbox_inches="tight", facecolor="#0d1117")
plt.close()
print("  ✅ 对比图: vote_system_report.png\n")
