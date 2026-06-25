#!/usr/bin/env python3
"""
完整回测 + 优化 + 报告 (先获取数据)
"""
import sys, os, json, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from btc_trader import *

# ============================================================
# 1. 获取数据 (重试机制)
# ============================================================
fetcher = DataFetcher()
strategies = get_all_strategies()

def fetch_retry(tf, count, retries=3):
    for i in range(retries):
        bars = fetcher.fetch_bars(tf, count)
        if len(bars) >= count * 0.5:
            return bars
        print(f"  ⚠️ 数据不足({len(bars)}), 等待后重试({i+1}/{retries})...")
        time.sleep(2)
    return bars

print("📡 获取数据...")
bars_4h = fetch_retry("4h", 2200)
bars_1d = fetch_retry("1d", 400)

if len(bars_4h) < 50:
    print("❌ 4h数据不足, 退出")
    sys.exit(1)

print(f"\n✅ 4h: {len(bars_4h)}根 ({bars_4h[0].time.date()} ~ {bars_4h[-1].time.date()})")
print(f"✅ 1d: {len(bars_1d)}根 ({bars_1d[0].time.date()} ~ {bars_1d[-1].time.date()})")

# ============================================================
# 2. 基础回测 (4h + 1d)
# ============================================================
print("\n" + "=" * 55)
print("  基础回测 - 4h")
print("=" * 55)
for i, s in enumerate(strategies):
    r = Backtester.run(bars_4h, s, initial_capital=10000)
    if r.total_trades == 0:
        print(f"  [{i}] {s.name:20s} → ⛔ 未开单")
        continue
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    print(f"  [{i}] {s.name:20s} → {pnl_s:>10s} ({r.total_pnl_pct:+.2f}%)  "
          f"{r.total_trades:3d}笔 胜率{r.win_rate:5.1f}% 回撤{r.max_drawdown:5.1f}% PF{r.profit_factor:.2f}")

print(f"\n{'='*55}")
print("  基础回测 - 日线")
print("="*55)
for i, s in enumerate(strategies):
    r = Backtester.run(bars_1d, s, initial_capital=10000,
                       risk_per_trade=25, trail_trigger=200, trail_back=80, sl_atr=2.0)
    if r.total_trades == 0:
        print(f"  [{i}] {s.name:20s} → ⛔ 未开单")
        continue
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    print(f"  [{i}] {s.name:20s} → {pnl_s:>10s} ({r.total_pnl_pct:+.2f}%)  "
          f"{r.total_trades:3d}笔 胜率{r.win_rate:5.1f}% 回撤{r.max_drawdown:5.1f}% PF{r.profit_factor:.2f}")

# ============================================================
# 3. 参数优化: EMARibbon (4h)
# ============================================================
print(f"\n{'='*55}")
print("  参数优化: EMARibbon (4h) — 第一轮")
print("="*55)

combos = [
    (15, 1.5, 40, 15), (15, 1.5, 60, 25), (15, 2.0, 60, 25),
    (18, 1.5, 40, 15), (18, 1.5, 60, 25), (18, 1.5, 80, 30), (18, 2.0, 80, 40), (18, 3.0, 120, 60),
    (20, 1.2, 60, 25), (20, 1.5, 40, 15), (20, 1.5, 60, 25), (20, 1.5, 80, 30), (20, 2.0, 60, 25),
    (20, 2.0, 100, 40), (20, 2.5, 120, 50), (20, 3.0, 150, 60),
    (22, 1.5, 40, 15), (22, 1.5, 60, 25), (22, 2.0, 60, 25),
    (25, 1.5, 60, 25),
]

opt_results = []
for adx_th, sl, tt, tb in combos:
    r = Backtester.run(bars_4h, strategies[1], risk_per_trade=25,
                       trail_trigger=tt, trail_back=tb, sl_atr=sl)
    net = r.total_pnl - r.total_trades * 1.0
    opt_results.append((adx_th, sl, tt, tb, r, net))

opt_results.sort(key=lambda x: x[5], reverse=True)

print(f"\n  {'排名':>4s} {'配置':35s} {'净盈亏':>10s} {'去佣':>8s} {'交易':>5s} {'胜率':>6s} {'回撤':>6s} {'PF':>5s}")
print("  " + "-"*85)
for rank, (adx_th, sl, tt, tb, r, net) in enumerate(opt_results[:15]):
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    medal = "🏆" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1:2d}"
    print(f"  {medal} ADX>{adx_th:2d} SL{sl:.1f}x T{tt:3d}/{tb:>2d} {pnl_s:>10s} {net_s:>8s} {r.total_trades:5d} {r.win_rate:5.1f}% {r.max_drawdown:5.1f}% {r.profit_factor:5.2f}")

# ============================================================
# 第二轮: H4EMA20 + 大止损 (追求每笔利润)
# ============================================================
print(f"\n{'='*55}")
print("  第二轮: 大止损 + 大追踪 (H4EMA20)")
print("="*55)

combos2 = []
for risk in [25, 50, 100]:
    for sl in [2.0, 3.0, 4.0]:
        for tt, tb in [(100, 40), (120, 50), (150, 60), (200, 80), (300, 120)]:
            combos2.append((risk, sl, tt, tb))

opt2 = []
for risk, sl, tt, tb in combos2:
    r = Backtester.run(bars_4h, strategies[0], risk_per_trade=risk,
                       trail_trigger=tt, trail_back=tb, sl_atr=sl)
    net = r.total_pnl - r.total_trades * 1.0
    opt2.append((risk, sl, tt, tb, r, net))

opt2.sort(key=lambda x: x[5], reverse=True)

print(f"\n  {'排名':>4s} {'配置':40s} {'净盈亏':>10s} {'去佣':>8s} {'交易':>5s} {'胜率':>6s} {'回撤':>6s} {'PF':>5s}")
print("  " + "-"*90)
for rank, (risk, sl, tt, tb, r, net) in enumerate(opt2[:15]):
    pnl_s = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    net_s = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
    medal = "🏆" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1:2d}"
    print(f"  {medal} Risk${risk:3d} SL{sl:.1f}x T{tt:3d}/{tb:>2d}     {pnl_s:>10s} {net_s:>8s} {r.total_trades:5d} {r.win_rate:5.1f}% {r.max_drawdown:5.1f}% {r.profit_factor:5.2f}")

# ============================================================
# 从两轮中选择最佳
# ============================================================
all_results = [(f"EMARibbon ADX>{a}", r, net) for a, sl, tt, tb, r, net in opt_results]
all_results += [(f"H4EMA20 Risk${rsk} SL{sl}x", r, net) for rsk, sl, tt, tb, r, net in opt2]
all_results.sort(key=lambda x: x[2], reverse=True)

best_name, best_r, best_net = all_results[0]

# ============================================================
# 4. 最佳方案详细报告
# ============================================================
best_combo = opt_results[0]
best_adx, best_sl, best_tt, best_tb, best_r, best_net = best_combo

print(f"\n{'='*55}")
print("  🏆 最佳方案")
print("="*55)
print(f"  策略:     {best_name}")
print(f"  年收益:   +${best_r.total_pnl:.2f} ({best_r.total_pnl_pct:+.2f}%)")
print(f"  去佣金:   ${best_net:.2f}")
print(f"  交易:     {best_r.total_trades}笔")
print(f"  胜率:     {best_r.win_rate:.1f}%")
print(f"  最大回撤: {best_r.max_drawdown:.1f}%")
print(f"  盈亏比:   {best_r.profit_factor:.2f}")
print(f"  夏普率:   {best_r.sharpe:.2f}")
print(f"  平均盈利: ${best_r.avg_win:.2f}")
print(f"  平均亏损: -${best_r.avg_loss:.2f}")

# ============================================================
# 5. 生成图片
# ============================================================
print(f"\n📈 生成报告...")

fig, axes = plt.subplots(3, 1, figsize=(14, 14), sharex=True,
                         gridspec_kw={"height_ratios": [3, 2, 2]})
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

colors = ["#58a6ff", "#FF9800", "#3fb950", "#f85149"]
names = [s.name for s in strategies]

# 图1: 4h对比
ax = axes[0]
for idx, s in enumerate(strategies):
    r = Backtester.run(bars_4h, s, initial_capital=10000)
    if r.total_trades == 0: continue
    times = [ep.time for ep in r.equity_curve]
    eqs = [ep.equity for ep in r.equity_curve]
    ax.plot(times, eqs, colors[idx], lw=1.2, alpha=0.85,
            label=f"{names[idx]} (${r.total_pnl:.0f})")
ax.axhline(10000, color="#30363d", ls="--", alpha=0.5)
ax.legend(fontsize=9, loc="upper left", facecolor="#161b22", labelcolor="#c9d1d9")
ax.set_title("4h 回测对比 — 全部策略 (2025.06 ~ 2026.06)", fontsize=13, fontweight="bold", color="#f0f6fc")
ax.set_ylabel("净值 ($)", fontsize=10)
ax.grid(True, alpha=0.1, color="#30363d")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# 图2: 最佳策略净值
ax = axes[1]
times = [ep.time for ep in best_r.equity_curve]
eqs = [ep.equity for ep in best_r.equity_curve]
ax.fill_between(times, 10000, eqs, where=[e>=10000 for e in eqs],
                color="#3fb950", alpha=0.1)
ax.fill_between(times, 10000, eqs, where=[e<10000 for e in eqs],
                color="#f85149", alpha=0.08)
ax.plot(times, eqs, "#FF9800", lw=1.5)
ax.axhline(10000, color="#30363d", ls="--", alpha=0.5)
ax.set_title(f'🏆 冠军: {best_name}  (${best_r.total_pnl:.2f})', 
             fontsize=12, fontweight="bold", color="#f0f6fc")
ax.set_ylabel("净值 ($)", fontsize=10)
ax.grid(True, alpha=0.1, color="#30363d")

# 图3: 回撤
ax = axes[2]
dds = [ep.drawdown for ep in best_r.equity_curve]
ax.fill_between(times, 0, dds, color="#f85149", alpha=0.25)
ax.plot(times, dds, "#f85149", lw=1)
ax.axhline(-3, color="#FF9800", ls="--", alpha=0.3, lw=0.8)
ax.axhline(-5, color="#f85149", ls="--", alpha=0.3, lw=0.8)
ax.set_ylabel("回撤 (%)", fontsize=10)
ax.set_xlabel("时间", fontsize=10, color="#c9d1d9")
ax.invert_yaxis()
ax.grid(True, alpha=0.1, color="#30363d")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

plt.tight_layout()
final_img = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_final_report.png")
plt.savefig(final_img, dpi=150, bbox_inches="tight", facecolor="#0d1117")
plt.close()
print(f"  ✅ 报告图: {final_img}")

# ============================================================
# 6. 保存JSON
# ============================================================
report_data = {
    "generated": "2026-06-22",
    "4h_data": f"{bars_4h[0].time.date()} ~ {bars_4h[-1].time.date()} ({len(bars_4h)}根)",
    "4h_results": [],
    "recommendation": {
        "strategy": best_name,
        "annual_pnl": round(best_r.total_pnl, 2),
        "annual_return_pct": round(best_r.total_pnl_pct, 2),
        "net_after_commission": round(best_net, 2),
        "trades": best_r.total_trades,
        "win_rate": round(best_r.win_rate, 1),
        "max_dd": round(best_r.max_drawdown, 2),
        "profit_factor": round(best_r.profit_factor, 2),
        "sharpe": round(best_r.sharpe, 2)
    }
}

for i, s in enumerate(strategies):
    r = Backtester.run(bars_4h, s)
    report_data["4h_results"].append({
        "strategy": s.name,
        "pnl": round(r.total_pnl, 2),
        "return_pct": round(r.total_pnl_pct, 2),
        "trades": r.total_trades,
        "win_rate": round(r.win_rate, 1),
        "max_dd": round(r.max_drawdown, 2)
    })

json_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_final_result.json")
with open(json_out, "w") as f:
    json.dump(report_data, f, ensure_ascii=False, indent=2)
print(f"  ✅ 数据报告: {json_out}")

print(f"\n{'='*55}")
print(f"  🎯 回测完成!")
print(f"  最佳: {best_name} → ${best_r.total_pnl:.2f}")
print(f"  去佣金后: ${best_net:.2f}")
print(f"{'='*55}")
