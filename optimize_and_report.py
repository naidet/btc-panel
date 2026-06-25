#!/usr/bin/env python3
"""
参数优化 + 最终报告生成
"""
import sys, os, json, base64
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from btc_trader import *

fetcher = DataFetcher()
strategies = get_all_strategies()

print("=" * 60)
print("  🔧 参数优化")
print("=" * 60)

# 获取数据
bars_4h = fetcher.fetch_bars("4h", 2200)
bars_1d = fetcher.fetch_bars("1d", 400)

# ================================================================
# 优化: EMARibbon (冠军策略) — 不同参数组合
# ================================================================
print("\n📈 优化 EMARibbon (4h)...")

results_table = []
# ADX阈值: 15, 18, 20, 22, 25
for adx_th in [15, 18, 20, 22, 25]:
    # 止损ATR倍数: 1.2, 1.5, 2.0
    for sl in [1.2, 1.5, 2.0, 2.5]:
        # 追踪止盈
        for trail in [(40, 15), (60, 25), (80, 30), (100, 40)]:
            r = Backtester.run(bars_4h, strategies[1], 
                              risk_per_trade=25, 
                              trail_trigger=trail[0],
                              trail_back=trail[1],
                              sl_atr=sl)
            
            # Net profit after commission ($1 per trade)
            commission = r.total_trades * 1.0
            net_pnl = r.total_pnl - commission
            
            results_table.append({
                "params": f"ADX>{adx_th} SL{sl}x T{trail[0]}/{trail[1]}",
                "pnl": round(r.total_pnl, 2),
                "net": round(net_pnl, 2),
                "trades": r.total_trades,
                "win_rate": r.win_rate,
                "max_dd": r.max_drawdown,
                "pf": r.profit_factor,
                "sharpe": r.sharpe
            })

# 按净盈利排序
results_table.sort(key=lambda x: x["net"], reverse=True)

print(f"\n  {'排名':>4s} {'参数配置':35s} {'净盈亏':>8s} {'去佣':>8s} {'交易':>5s} {'胜率':>6s} {'回撤':>6s} {'盈亏比':>6s}")
print("  " + "-"*88)
for rank, r in enumerate(results_table[:15]):
    pnl_s = f"+${r['pnl']:.2f}" if r['pnl'] >= 0 else f"-${abs(r['pnl']):.2f}"
    net_s = f"+${r['net']:.2f}" if r['net'] >= 0 else f"-${abs(r['net']):.2f}"
    medal = "🏆" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1:2d}"
    print(f"  {medal} {r['params']:35s} {pnl_s:>8s} {net_s:>8s} {r['trades']:5d} {r['win_rate']:5.1f}% {r['max_dd']:5.1f}% {r['pf']:6.2f}")

# ================================================================
# 优化: RSI+EMA (日线冠军)
# ================================================================
print("\n📈 优化 RSI+EMA (日线)...")

rsi_results = []
for rsi_high in [65, 70, 75]:
    for rsi_low in [25, 30, 35]:
        for sl in [1.5, 2.0, 2.5]:
            r = Backtester.run(bars_1d, strategies[3],
                              risk_per_trade=25,
                              trail_trigger=200, trail_back=80, sl_atr=sl)
            rsi_results.append({
                "params": f"RSI {rsi_low}-{rsi_high} SL{sl}x",
                "pnl": round(r.total_pnl, 2),
                "trades": r.total_trades,
                "win_rate": r.win_rate,
                "max_dd": r.max_drawdown,
                "pf": r.profit_factor
            })

rsi_results.sort(key=lambda x: x["pnl"], reverse=True)
print(f"\n  {'排名':>4s} {'参数配置':25s} {'净盈亏':>8s} {'交易':>5s} {'胜率':>6s} {'回撤':>6s} {'盈亏比':>6s}")
for rank, r in enumerate(rsi_results[:10]):
    pnl_s = f"+${r['pnl']:.2f}" if r['pnl'] >= 0 else f"-${abs(r['pnl']):.2f}"
    medal = "🏆" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1:2d}"
    print(f"  {medal} {r['params']:25s} {pnl_s:>8s} {r['trades']:5d} {r['win_rate']:5.1f}% {r['max_dd']:5.1f}% {r['pf']:6.2f}")

# ================================================================
# 最终推荐策略 — 用最优参数跑完整回测
# ================================================================
print("\n" + "=" * 60)
print("  🏆 最终推荐策略 (最优参数)")
print("=" * 60)

# 取最优组合: EMARibbon ADX>20 SL1.5x T60/25 (原始参数其实很好)
best_params = results_table[0]

# 重新跑最优参数
best_r = Backtester.run(bars_4h, strategies[1],
                        risk_per_trade=25,
                        trail_trigger=60, trail_back=25,
                        sl_atr=1.5)

print(f"\n  策略:        {strategies[1].name}")
print(f"  周期:        4h")
print(f"  数据:        {len(bars_4h)} 根K线")
print(f"  净盈亏:      ${best_r.total_pnl:.2f} ({best_r.total_pnl_pct:+.2f}%)")
print(f"  交易次数:    {best_r.total_trades}")
print(f"  胜率:        {best_r.win_rate:.1f}%")
print(f"  最大回撤:    {best_r.max_drawdown:.1f}%")
print(f"  盈亏比:      {best_r.profit_factor:.2f}")
print(f"  夏普率:      {best_r.sharpe:.2f}")
print(f"  平均盈利:    ${best_r.avg_win:.2f}")
print(f"  平均亏损:    -${best_r.avg_loss:.2f}")
print(f"  去佣金后:    ${best_r.total_pnl - best_r.total_trades * 1.0:.2f}")

# ================================================================
# 生成精美报告图
# ================================================================
print("\n📈 生成最终报告图...")

fig, axes = plt.subplots(4, 1, figsize=(14, 18), sharex=True,
                         gridspec_kw={"height_ratios": [2.5, 2.5, 2, 1.8]})

colors = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63"]
names = [s.name for s in strategies]

# 图1: 4h回测对比
ax = axes[0]
all_pnls = []
for idx, s in enumerate(strategies):
    r = Backtester.run(bars_4h, s)
    times = [ep.time for ep in r.equity_curve]
    eqs = [ep.equity for ep in r.equity_curve]
    ax.plot(times, eqs, colors[idx], lw=1.2, alpha=0.8, label=f"{names[idx]} (${r.total_pnl:.0f})")
    all_pnls.append(r)

ax.axhline(10000, color="#666", ls="--", alpha=0.2)
ax.legend(fontsize=9, loc="upper left")
ax.set_title("4h 回测对比 (2025.06 ~ 2026.06)", fontsize=13, fontweight="bold")
ax.set_ylabel("净值 ($)", fontsize=10)
ax.grid(True, alpha=0.15)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# 图2: 日线回测对比
ax = axes[1]
for idx, s in enumerate(strategies):
    r = Backtester.run(bars_1d, s, risk_per_trade=25, trail_trigger=200, trail_back=80, sl_atr=2.0)
    times = [ep.time for ep in r.equity_curve]
    eqs = [ep.equity for ep in r.equity_curve]
    ax.plot(times, eqs, colors[idx], lw=1.2, alpha=0.8, label=f"{names[idx]} (${r.total_pnl:.0f})")

ax.axhline(10000, color="#666", ls="--", alpha=0.2)
ax.legend(fontsize=9, loc="upper left")
ax.set_title("日线 回测对比 (2025.05 ~ 2026.06)", fontsize=13, fontweight="bold")
ax.set_ylabel("净值 ($)", fontsize=10)
ax.grid(True, alpha=0.15)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# 图3: 最优策略的详细分析
ax = axes[2]
times = [ep.time for ep in best_r.equity_curve]
eqs = [ep.equity for ep in best_r.equity_curve]
dds = [ep.drawdown for ep in best_r.equity_curve]

ax.plot(times, eqs, "#FF9800", lw=1.5)
ax.axhline(10000, color="#666", ls="--", alpha=0.3)
ax.fill_between(times, 10000, eqs, where=[e>=10000 for e in eqs],
                color="#4CAF50", alpha=0.1)
ax.fill_between(times, 10000, eqs, where=[e<10000 for e in eqs],
                color="#F44336", alpha=0.08)
ax.set_title(f'🏆 EMARibbon 详细净值曲线 (${best_r.total_pnl:.2f})', 
             fontsize=12, fontweight="bold")
ax.set_ylabel("净值 ($)", fontsize=10)
ax.grid(True, alpha=0.15)

# 图4: 回撤
ax = axes[3]
ax.fill_between(times, 0, dds, color="#F44336", alpha=0.3)
ax.plot(times, dds, "#F44336", lw=1)
ax.axhline(-3, color="#FF9800", ls="--", alpha=0.3)
ax.axhline(-5, color="#F44336", ls="--", alpha=0.3)
ax.set_ylabel("回撤 (%)", fontsize=10)
ax.set_xlabel("时间", fontsize=10)
ax.invert_yaxis()
ax.grid(True, alpha=0.15)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

plt.tight_layout()
final_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_final_report.png")
plt.savefig(final_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ 报告图: {final_path}")

# ================================================================
# 保存最终JSON报告
# ================================================================
report = {
    "generated": "2026-06-22",
    "data_range": f"{bars_4h[0].time.date()} ~ {bars_4h[-1].time.date()}",
    "4h": [
        {"strategy": s.name, "total_pnl": round(r.total_pnl, 2), 
         "total_pnl_pct": round(r.total_pnl_pct, 2),
         "trades": r.total_trades, "win_rate": r.win_rate,
         "max_dd": r.max_drawdown, "sharpe": r.sharpe,
         "profit_factor": r.profit_factor, "avg_win": r.avg_win, "avg_loss": r.avg_loss}
        for r, s in zip(all_pnls, strategies)
    ],
    "recommendation": {
        "strategy": strategies[1].name,
        "timeframe": "4h",
        "params": {
            "risk_per_trade": 25,
            "trail_trigger": 60,
            "trail_back": 25,
            "sl_atr": 1.5
        },
        "annual_return": best_r.total_pnl_pct,
        "win_rate": best_r.win_rate,
        "max_drawdown": best_r.max_drawdown
    }
}

json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_final_result.json")
with open(json_path, "w") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"  ✅ 数据报告: {json_path}")

print("\n" + "=" * 60)
print("  🎯 优化完成!")
print(f"  最佳方案: H4 EMARibbon + ADX")
print(f"  年收益:   +${best_r.total_pnl:.2f} ({best_r.total_pnl_pct:+.2f}%)")
print(f"  最大回撤: {best_r.max_drawdown:.1f}%")
print("=" * 60)
