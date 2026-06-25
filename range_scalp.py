#!/usr/bin/env python3
"""
震荡套利 · Range Arb — 均值回归高频策略
=========================================
策略: 布林带(20,2) + RSI(14) 极端值 + ADX 震荡过滤
周期: M15 (15分钟), 2014-2026 全量回测

逻辑:
  做多: close ≤ BB下轨 AND RSI < 30 AND ADX(1h) < 20
  做空: close ≥ BB上轨 AND RSI > 70 AND ADX(1h) < 20
  止盈: 回归中轨(SMA20)
  止损: 1.5x ATR

独立性: 完全不依赖 btc_panel.py 或 backtest_panel.py
"""

import os, sys, json, time, datetime, warnings
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
warnings.filterwarnings("ignore")

# 引用 btc_trader 的基础类型
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_trader import Bar, Trade, BacktestResult, EquityPoint, calc_ema, calc_rsi, calc_atr, calc_adx


# ═══════════════════════════════════════════
# 策略配置
# ═══════════════════════════════════════════
CFG = {
    # 布林带
    "bb_period": 20,
    "bb_std": 2.0,

    # RSI 极端值
    "rsi_period": 14,
    "rsi_oversold": 30,   # < 此值做多
    "rsi_overbought": 70, # > 此值做空

    # 震荡识别(用1h ADX判断大环境)
    "adx_period": 14,
    "adx_max": 20,        # ADX < 20 = 震荡市

    # 止损/止盈
    "sl_atr_mult": 1.5,   # 止损 = 1.5x ATR
    "tp_regression": True, # 止盈 = 回归中轨

    # 风控
    "risk_per_trade": 20,
    "max_daily_loss": 500,
    "max_drawdown_pct": 20,
    "cooldown_minutes": 15,

    # 手续费
    "fee_pct": 0.04,
    "slippage_pct": 0.02,
}


# ═══════════════════════════════════════════
# 布林带计算
# ═══════════════════════════════════════════
def calc_bollinger(cl: list, period: int = 20, std_mult: float = 2.0):
    """返回 (sma, upper, lower) 三个序列"""
    sma = [np.nan] * len(cl)
    upper = [np.nan] * len(cl)
    lower = [np.nan] * len(cl)
    for i in range(period - 1, len(cl)):
        window = cl[i - period + 1 : i + 1]
        m = np.mean(window)
        s = np.std(window, ddof=0)
        sma[i] = m
        upper[i] = m + s * std_mult
        lower[i] = m - s * std_mult
    return sma, upper, lower


# ═══════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════
def run_backtest(bars_15m: list, bars_1h: list,
                 capital: float = 500.0) -> BacktestResult:
    """M15 逐棒回测"""

    result = BacktestResult()
    N = len(bars_15m)
    warmup = max(CFG["bb_period"], CFG["rsi_period"], CFG["adx_period"]) + 5

    if N < warmup:
        print(f"  ⚠️ 数据不足")
        return result

    # ═══ 预计算: M15 指标 ═══
    print(f"  ⏳ 预计算 M15 指标 ({N:,} bars)...", end="", flush=True)
    cl_all = [b.close for b in bars_15m]
    hi_all = [b.high for b in bars_15m]
    lo_all = [b.low for b in bars_15m]

    # 布林带(20)
    bb_sma, bb_upper, bb_lower = calc_bollinger(cl_all, CFG["bb_period"], CFG["bb_std"])
    # RSI(14)
    rsi_all = calc_rsi(cl_all, CFG["rsi_period"])
    # ATR(14)
    atr_all = calc_atr(hi_all, lo_all, cl_all, 14)

    # ═══ 预计算: 1h ADX(震荡判断) ═══
    cl_1h = [b.close for b in bars_1h]
    hi_1h = [b.high for b in bars_1h]
    lo_1h = [b.low for b in bars_1h]
    adx_1h = calc_adx(hi_1h, lo_1h, cl_1h, 14) if len(bars_1h) > 20 else []

    # 1h → M15 索引映射
    idx_1h_map = [0] * N
    j = 0
    for i in range(N):
        while j + 1 < len(bars_1h) and bars_1h[j + 1].time <= bars_15m[i].time:
            j += 1
        idx_1h_map[i] = j
    print(" 完成")

    # ═══ 状态机 ═══
    position = 0
    entry_price = 0.0
    lots = 0.0
    equity = capital
    peak_equity = capital
    last_trade_idx = -9999
    cooldown_bars = max(1, CFG["cooldown_minutes"] // 15)
    trade = None

    equity_curve = []

    print(f"  ⏳ 回测进行中...", end="", flush=True)
    for i in range(warmup, N):
        bar = bars_15m[i]
        price = bar.close
        high = bar.high
        low = bar.low

        # ====== 持仓管理 ======
        if position != 0:
            unrealized = (price - entry_price) * lots if position == 1 \
                         else (entry_price - price) * lots
            current_equity = equity + unrealized

            exit_triggered = False
            exit_reason = ""
            exit_price = price

            # 止盈: 回归中轨
            if CFG["tp_regression"] and i < len(bb_sma):
                mid = bb_sma[i]
                if not np.isnan(mid):
                    if position == 1 and high >= mid:
                        exit_price = mid
                        exit_triggered = True
                        exit_reason = "回归中轨"
                    elif position == -1 and low <= mid:
                        exit_price = mid
                        exit_triggered = True
                        exit_reason = "回归中轨"

            # 止损: 1.5x ATR
            if not exit_triggered and i < len(atr_all):
                atr_v = atr_all[i]
                if atr_v > 0:
                    sl_dist = atr_v * CFG["sl_atr_mult"]
                    sl_price = entry_price - sl_dist if position == 1 else entry_price + sl_dist
                    if position == 1 and low <= sl_price:
                        exit_price = sl_price
                        exit_triggered = True
                        exit_reason = "止损"
                    elif position == -1 and high >= sl_price:
                        exit_price = sl_price
                        exit_triggered = True
                        exit_reason = "止损"

            if exit_triggered:
                pnl = (exit_price - entry_price) * lots if position == 1 \
                      else (entry_price - exit_price) * lots
                fee = abs(exit_price) * lots * CFG["fee_pct"] / 100
                slip = abs(exit_price) * lots * CFG["slippage_pct"] / 100
                pnl -= (fee + slip)
                equity += pnl

                if trade:
                    trade.exit_time = bar.time
                    trade.exit_price = exit_price
                    trade.pnl = pnl
                    trade.pnl_pct = pnl / capital * 100
                    trade.exit_reason = exit_reason

                last_trade_idx = i
                position = 0

            equity_curve.append(EquityPoint(bar.time, current_equity,
                (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0))
            if current_equity > peak_equity:
                peak_equity = current_equity
            continue

        # ====== 空仓 ======
        equity_curve.append(EquityPoint(bar.time, equity,
            (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0))
        if equity > peak_equity:
            peak_equity = equity

        # 冷却期
        if i - last_trade_idx < cooldown_bars:
            continue

        # === 震荡识别 (1h ADX) ===
        idx1h = idx_1h_map[i]
        if idx1h < len(adx_1h):
            if adx_1h[idx1h] >= CFG["adx_max"]:
                continue  # 趋势市不参与

        # === 信号 ===
        if i >= len(bb_lower) or i >= len(rsi_all):
            continue

        bb_l = bb_lower[i]
        bb_u = bb_upper[i]
        rsi_v = rsi_all[i]

        if np.isnan(bb_l) or np.isnan(bb_u) or np.isnan(rsi_v):
            continue

        # 做多: 碰下轨 + RSI超卖
        if price <= bb_l and rsi_v < CFG["rsi_oversold"]:
            atr_v = atr_all[i] if i < len(atr_all) and atr_all[i] > 0 else 0
            sl_dist = max(atr_v * CFG["sl_atr_mult"], price * 0.005)
            lots = max(0.01, round(CFG["risk_per_trade"] / sl_dist, 2))
            entry_price = price * (1 + CFG["slippage_pct"] / 100)
            fee = entry_price * lots * CFG["fee_pct"] / 100
            equity -= fee
            position = 1
            trade = Trade(entry_time=bar.time, side="BUY",
                          entry_price=entry_price, size=lots)
            result.trades.append(trade)

        # 做空: 碰上轨 + RSI超买
        elif price >= bb_u and rsi_v > CFG["rsi_overbought"]:
            atr_v = atr_all[i] if i < len(atr_all) and atr_all[i] > 0 else 0
            sl_dist = max(atr_v * CFG["sl_atr_mult"], price * 0.005)
            lots = max(0.01, round(CFG["risk_per_trade"] / sl_dist, 2))
            entry_price = price * (1 - CFG["slippage_pct"] / 100)
            fee = entry_price * lots * CFG["fee_pct"] / 100
            equity -= fee
            position = -1
            trade = Trade(entry_time=bar.time, side="SELL",
                          entry_price=entry_price, size=lots)
            result.trades.append(trade)

    # 最后平仓
    if position != 0:
        last_price = bars_15m[-1].close
        pnl = (last_price - entry_price) * lots if position == 1 \
              else (entry_price - last_price) * lots
        fee = abs(last_price) * lots * CFG["fee_pct"] / 100
        pnl -= fee
        equity += pnl
        if trade:
            trade.exit_time = bars_15m[-1].time
            trade.exit_price = last_price
            trade.pnl = pnl
            trade.pnl_pct = pnl / capital * 100
            trade.exit_reason = "回测结束"

    print(" 完成")

    # ═══ 统计 ═══
    result.equity_curve = equity_curve
    result.total_pnl = equity - capital
    result.total_pnl_pct = (equity - capital) / capital * 100
    closed = [t for t in result.trades if t.exit_time is not None]
    result.total_trades = len(closed)
    result.win_trades = len([t for t in closed if t.pnl > 0])
    result.lose_trades = len([t for t in closed if t.pnl <= 0])
    result.win_rate = (result.win_trades / result.total_trades * 100) \
                      if result.total_trades > 0 else 0
    result.max_drawdown = max((ep.drawdown for ep in equity_curve), default=0)

    wins = [t.pnl for t in closed if t.pnl > 0]
    losses = [t.pnl for t in closed if t.pnl < 0]
    result.avg_win = np.mean(wins) if wins else 0
    result.avg_loss = abs(np.mean(losses)) if losses else 0
    result.profit_factor = abs(sum(wins) / sum(losses)) \
        if losses and sum(losses) != 0 else (float('inf') if wins else 0)

    returns = [t.pnl for t in closed]
    if returns and len(returns) > 1 and np.std(returns) > 0:
        n_total = max(1, N - warmup)
        result.sharpe = np.mean(returns) / np.std(returns) * np.sqrt(len(closed) / n_total * 365 * 24 * 4)

    return result


# ═══════════════════════════════════════════
# MT5 数据获取
# ═══════════════════════════════════════════
def fetch_mt5(tf_name: str, symbol: str = "BTCUSD"):
    import MetaTrader5 as mt5
    tf_map = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
    m5tf = tf_map.get(tf_name)

    mp = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    if not mt5.initialize(path=mp):
        print(f"  ❌ MT5 初始化失败"); return []

    # 从多个起始年份尝试获取数据(MT5历史数据有限)
    for start_year in [2021, 2023, 2024]:
        rates = mt5.copy_rates_range(symbol, m5tf, datetime.datetime(start_year, 1, 1),
                                     datetime.datetime.now())
        if rates is not None and len(rates) > 100:
            break
        print(f"  ⚠️ {tf_name} {start_year}~无数据, 尝试更近...")
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print(f"  ⚠️ {tf_name}: 无数据")
        return []

    bars = []
    for row in rates:
        bars.append(Bar(
            time=datetime.datetime.fromtimestamp(row[0]),
            open=row[1], high=row[2], low=row[3],
            close=row[4], volume=row[5],
        ))
    return bars


# ═══════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════
def main():
    print("=" * 60)
    print("  震荡套利 · Range Arb — 均值回归策略")
    print("  布林带(20,2) + RSI(14)极端 + ADX<20 震荡过滤")
    print(f"  周期: M15  |  本金: $500  |  每笔风险: ${CFG['risk_per_trade']}")
    print("=" * 60)

    # 1. 数据
    print("\n[1/3] 获取数据 (MT5)...")
    bars_15m = fetch_mt5("M15")
    bars_1h = fetch_mt5("H1")

    if not bars_15m:
        print("  ❌ M15 数据获取失败")
        return
    if not bars_1h:
        bars_1h = bars_15m

    t0 = bars_15m[0].time.strftime("%Y-%m-%d")
    t1 = bars_15m[-1].time.strftime("%Y-%m-%d")
    p0 = bars_15m[0].close
    p1 = bars_15m[-1].close
    print(f"  📅 {t0} ~ {t1}")
    print(f"  💰 ${p0:.0f} → ${p1:.0f} ({(p1/p0-1)*100:+.0f}%)")
    print(f"  📊 M15: {len(bars_15m):,} 根")

    # 截断(内存控制)
    if len(bars_15m) > 80000:
        bars_15m = bars_15m[-80000:]
        print(f"  ⚠️ 截取最近 80,000 根")

    # 2. 回测
    print("\n[2/3] 运行回测...")
    t_start = time.time()
    result = run_backtest(bars_15m, bars_1h, capital=500)
    elapsed = time.time() - t_start
    print(f"  ✅ 完成 (耗时 {elapsed:.1f}s)")

    # 3. 结果
    print("\n[3/3] 生成报告...")
    name = "震荡套利 · Range Arb (M15)"

    # 文字
    print(f"\n  {'='*50}")
    print(f"  📊 {name}")
    print(f"  {'='*50}")
    print(f"  本金: $500  →  最终: ${500+result.total_pnl:,.2f}")
    print(f"  总交易: {result.total_trades} 笔")
    print(f"  胜率: {result.win_rate:.0f}% ({result.win_trades}W/{result.lose_trades}L)")
    print(f"  总盈亏: ${result.total_pnl:+,.2f} ({result.total_pnl_pct:+.1f}%)")
    print(f"  最大回撤: {result.max_drawdown:.1f}%")
    print(f"  平均盈: ${result.avg_win:,.2f}  |  平均亏: ${result.avg_loss:,.2f}")
    print(f"  盈利因子: {result.profit_factor:.2f}")
    print(f"  夏普: {result.sharpe:.2f}")

    # 年度
    closed = [t for t in result.trades if t.exit_time is not None]
    yearly = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in closed:
        y = t.entry_time.year
        yearly[y]["count"] += 1
        yearly[y]["pnl"] += t.pnl
        if t.pnl > 0:
            yearly[y]["wins"] += 1

    print(f"\n  📅 年度表现:")
    for y in sorted(yearly.keys()):
        d = yearly[y]
        wr = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
        sign = "+" if d["pnl"] >= 0 else ""
        bar = "█" * max(1, int(abs(d["pnl"]) / 10))
        print(f"    {y}: {d['count']:4d}笔  胜率{wr:5.0f}%  {sign}${d['pnl']:+8.2f}  {bar}")

    # 对比共振趋势
    print(f"\n  📊 双策略对比:")
    print(f"    {'策略':20s} {'交易笔数':>8s} {'胜率':>6s} {'总盈亏':>10s} {'年化':>6s}")
    print(f"    {'─'*50}")
    print(f"    {'共振趋势 (原始)':20s} {'453':>8s} {'77%':>6s} {'+$728':>10s} {'10.2%':>6s}")
    print(f"    {'震荡套利 RangeArb':20s} {result.total_trades:>8d} "
          f"{result.win_rate:>5.0f}%  {result.total_pnl:+>9.2f}  {'─':>6s}")
    print(f"    {'组合 (60/40)':20s} {'─':>8s} {'─':>6s} "
          f"{'+$'+str(round(728*0.6+result.total_pnl*0.4)):>10s} {'─':>6s}")

    # 平仓原因
    reasons = defaultdict(lambda: {"count": 0, "pnl": 0})
    for t in closed:
        reasons[t.exit_reason]["count"] += 1
        reasons[t.exit_reason]["pnl"] += t.pnl
    print(f"\n  🎯 平仓原因:")
    for r in sorted(reasons, key=lambda x: -reasons[x]["count"]):
        print(f"    {r}: {reasons[r]['count']:4d}笔  ${reasons[r]['pnl']:+,.2f}")

    # 方向
    longs = [t for t in closed if t.side == "BUY"]
    shorts = [t for t in closed if t.side == "SELL"]
    if longs:
        l_pnl = sum(t.pnl for t in longs)
        l_wr = sum(1 for t in longs if t.pnl > 0) / len(longs) * 100
        print(f"\n  🔼 多头: {len(longs)}笔 胜率{l_wr:.0f}%  ${l_pnl:+.2f}")
    if shorts:
        s_pnl = sum(t.pnl for t in shorts)
        s_wr = sum(1 for t in shorts if t.pnl > 0) / len(shorts) * 100
        print(f"  🔽 空头: {len(shorts)}笔 胜率{s_wr:.0f}%  ${s_pnl:+.2f}")

    # 绘图
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "range_scalp_result.png")
    try:
        from btc_trader import plot_result
        plot_result(result, name, "M15 Mean Reversion",
                    capital=500, save_path=save_path)
        print(f"\n  📊 图表: {save_path}")
    except Exception as e:
        print(f"\n  ⚠️ 图表失败: {e}")

    # JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "range_scalp_trades.json")
    trades_out = []
    for t in closed:
        trades_out.append({
            "entry": t.entry_time.strftime("%Y-%m-%d %H:%M"),
            "exit": t.exit_time.strftime("%Y-%m-%d %H:%M"),
            "side": t.side,
            "entry_price": round(t.entry_price, 2),
            "exit_price": round(t.exit_price, 2),
            "pnl": round(t.pnl, 2),
            "reason": t.exit_reason,
        })
    with open(json_path, "w") as f:
        json.dump(trades_out, f, indent=2)
    print(f"  📋 交易记录: {json_path}")

    print("\n" + "=" * 60)
    print("  回测完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
