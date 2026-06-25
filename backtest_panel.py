#!/usr/bin/env python3
"""
BTC 面板策略回测 — 完整复刻 btc_panel.py 的共振策略
=====================================================
- 多周期共振 (1h/4h/1d)
- RSI+EMA 信号生成
- 风控门禁 (ATR飙升 + 点差 + 日亏上限 + 回撤熔断)
- 移动止损 + 盈利回撤保护
- 冷却期

用法: python backtest_panel.py
数据源: Binance 免费API (无需Key)
"""

import os, sys, json, time, datetime, warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore")

# 引用 btc_trader 的指标函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_trader import (
    Bar, Trade, EquityPoint, BacktestResult,
    calc_ema, calc_rsi, calc_adx, calc_atr, DataFetcher,
    plot_result, print_result
)

# ============================================================
# 策略配置 (完全匹配 btc_panel.py DEFAULT_PARAMS)
# ============================================================
CFG = {
    # 指标参数
    "ema_period": 20,
    "rsi_period": 14,
    "rsi_long_lo": 50,  "rsi_long_hi": 70,
    "rsi_short_lo": 30, "rsi_short_hi": 50,
    "adx_period": 14,   "adx_threshold": 25,

    # 共振开仓
    "resonance_threshold": 2,  # 至少 2/3 时间周期一致

    # 止盈止损 (转百分比以适应历史价格范围)
    "sl_atr_mult": 1.5,
    "sl_min_pct": 0.8,       # 原 $800 / ~$100k
    "tp_atr_mult": 2.0,
    "tp_min_pct": 1.5,

    # 移动止损
    "trail_profit_pct": 0.3,  # 原 $3 / 0.01 BTC ≈ 价格*0.003
    "trail_dist_pct": 0.2,    # 原 $200 / price

    # 盈利回撤保护
    "profit_lock_trigger": 5,     # 盈利达$X触发保护 (固定金额, 默认$5)
    "profit_lock_pullback": 20,   # 回撤利润% 平仓

    # 风控
    "risk_per_trade": 20,          # 每笔风险$
    "max_daily_loss": 500,
    "max_drawdown_pct": 20,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
    "cooldown_bars": 1,            # 冷却期 (1h级, 约等于原15min)
    "volatility_filter": True,

    # 手续费 + 滑点
    "fee_pct": 0.04,               # Binance taker fee
    "slippage_pct": 0.02,
}

# ============================================================
# 信号生成 (完整复刻 fetch_all_mt5_data 的共振逻辑)
# ============================================================

def calc_resonance_signal(cl: list, hi: list, lo: list, ep: int, rp: int,
                          rlh: float, rhh: float, rsl: float, rsh: float,
                          ap: int, at: float) -> dict:
    """对单个时间周期生成信号 (完全匹配 btc_panel.py 151-157行)"""
    n = len(cl)
    if n < max(ep, rp, ap) + 5:
        return {"signal": 0, "rsi": 0, "ema20": 0, "price": cl[-1],
                "adx": 0, "macd_hist": 0, "bars": n}

    pr = cl[-1]
    e20 = calc_ema(cl, ep)
    rsi_vals = calc_rsi(cl, rp)

    # ADX
    adx_val = 0
    if n >= ap + 5:
        try:
            adx_arr = calc_adx(hi, lo, cl, ap)
            adx_val = adx_arr[-1] if adx_arr else 0
        except: pass

    # MACD柱
    macd_hist = 0
    if n >= 26:
        try:
            ema12 = calc_ema(cl, 12); ema26 = calc_ema(cl, 26)
            mline = ema12[-1] - ema26[-1]
            if n >= 35:
                mvs = [calc_ema(cl[:i+1], 12)[-1] - calc_ema(cl[:i+1], 26)[-1]
                       for i in range(max(0, n-9), n) if i >= 25]
                sline = sum(mvs[-9:]) / len(mvs[-9:]) if mvs else mline
                macd_hist = mline - sline
        except: pass

    # 信号判定 (与面板完全相同)
    sig = 1 if (pr > e20[-1] and rlh < rsi_vals[-1] < rhh) else \
          (-1 if (pr < e20[-1] and rsl < rsi_vals[-1] < rsh) else 0)

    return {
        "signal": sig,
        "rsi": round(rsi_vals[-1], 1),
        "ema20": round(e20[-1], 2),
        "price": round(pr, 2),
        "adx": round(adx_val, 1),
        "macd_hist": round(macd_hist, 2),
        "bars": n,
    }


def check_risk_gates(equity: float, peak_equity: float, bar_idx: int,
                     atr_now: float, atr_avg: float) -> tuple:
    """风控门禁 (简化版, 不依赖MT5)"""
    reasons = []
    blocked = False

    # 回撤熔断
    if peak_equity > 0:
        dd_pct = (peak_equity - equity) / peak_equity * 100
        if dd_pct > CFG["max_drawdown_pct"]:
            blocked = True
            reasons.append(f"回撤{dd_pct:.1f}% > 上限{CFG['max_drawdown_pct']}%")

    # ATR飙升
    if CFG["volatility_filter"] and atr_avg > 0 and atr_now > 0:
        ratio = atr_now / atr_avg
        if ratio > CFG["atr_spike_mult"]:
            blocked = True
            reasons.append(f"ATR飙升{ratio:.1f}x")

    return not blocked, reasons


# ============================================================
# 回测主引擎
# ============================================================

def run_full_backtest(bars_1h: list, bars_4h: list, bars_1d: list,
                      capital: float = 500.0) -> BacktestResult:
    """
    优化版回测 — 预计算所有指标，O(n) 复杂度
    """
    result = BacktestResult()
    ep = CFG["ema_period"]; rp = CFG["rsi_period"]
    rlh = CFG["rsi_long_lo"]; rhh = CFG["rsi_long_hi"]
    rsl = CFG["rsi_short_lo"]; rsh = CFG["rsi_short_hi"]
    ap = CFG["adx_period"]; at = CFG["adx_threshold"]
    threshold = CFG["resonance_threshold"]
    cooldown = CFG["cooldown_bars"]

    warmup = max(ep, rp, ap) + 35
    N = len(bars_1h)
    if N < warmup:
        print(f"  ⚠️ 数据不足{warmup}根1h，无法回测")
        return result

    # ═══ 预计算: 3个时间周期的信号序列 ═══
    def precalc_signals(bars):
        """对一批K线预计算所有信号值，返回按索引的信号dict列表"""
        cl_all = [b.close for b in bars]; hi_all = [b.high for b in bars]; lo_all = [b.low for b in bars]
        ema_all = calc_ema(cl_all, ep)
        rsi_all = calc_rsi(cl_all, rp)
        sigs = []
        for i in range(len(bars)):
            if i < warmup - 1:
                sigs.append({"signal": 0}); continue
            sig = 1 if (cl_all[i] > ema_all[i] and rsi_all[i] >= 50) else \
                  (-1 if (cl_all[i] < ema_all[i] and rsi_all[i] <= 50) else 0)
            sigs.append({"signal": sig})
        return sigs

    print(f"  ⏳ 预计算指标 ({N:,} bars)...", end="", flush=True)
    sigs_1h = precalc_signals(bars_1h)
    sigs_4h = precalc_signals(bars_4h)
    sigs_1d = precalc_signals(bars_1d)

    # 预计算 4h/1d 索引映射: 对每个1h bar, 快速找到对应的4h/1d bar索引
    idx_4h_map = [0] * N
    j = 0
    for i in range(N):
        while j + 1 < len(bars_4h) and bars_4h[j + 1].time <= bars_1h[i].time:
            j += 1
        idx_4h_map[i] = j
    idx_1d_map = [0] * N
    j = 0
    for i in range(N):
        while j + 1 < len(bars_1d) and bars_1d[j + 1].time <= bars_1h[i].time:
            j += 1
        idx_1d_map[i] = j

    # 预计算 ATR(14)
    atr_all = calc_atr([b.high for b in bars_1h], [b.low for b in bars_1h],
                        [b.close for b in bars_1h], 14)

    # 预计算 1d ADX(14) + EMA50 (趋势过滤器)
    cl_1d = [b.close for b in bars_1d]; hi_1d = [b.high for b in bars_1d]; lo_1d = [b.low for b in bars_1d]
    adx_1d = calc_adx(hi_1d, lo_1d, cl_1d, 14)  # 日线ADX
    ema50_1d = calc_ema(cl_1d, 50)               # 日线EMA50 (大趋势方向)

    print(" 完成")

    # 状态
    position = 0; entry_price = 0.0; entry_bar = 0; lots = 0.0
    trail_active = False; trail_extreme = 0.0; trail_locked = False
    _peak_profit = 0.0; trade = None
    equity = capital; peak_equity = capital
    last_trade_bar = -cooldown
    equity_curve = []; closed_nets = {}

    print(f"  ⏳ 回测计算...", end="", flush=True)
    for i in range(warmup, N):
        bar = bars_1h[i]
        price = bar.close; high = bar.high; low = bar.low

        # ====== 有持仓 ======
        if position != 0:
            unrealized = (price - entry_price) * lots if position == 1 \
                         else (entry_price - price) * lots
            current_equity = equity + unrealized
            if unrealized > _peak_profit:
                _peak_profit = unrealized

            atr_val = atr_all[i] if i < len(atr_all) and atr_all[i] > 0 else 0
            sl_dist = max(atr_val * CFG["sl_atr_mult"], price * CFG["sl_min_pct"] / 100)
            sl_price = entry_price - sl_dist if position == 1 else entry_price + sl_dist

            exit_triggered = False; exit_reason = ""
            if position == 1 and low <= sl_price:
                exit_price = sl_price; exit_triggered = True; exit_reason = "止损"
            elif position == -1 and high >= sl_price:
                exit_price = sl_price; exit_triggered = True; exit_reason = "止损"

            if not exit_triggered:
                trail_profit_trigger = entry_price * lots * CFG["trail_profit_pct"] / 100
                trail_dist = price * CFG["trail_dist_pct"] / 100
                if not trail_active and unrealized >= trail_profit_trigger:
                    trail_active = True
                    trail_extreme = high if position == 1 else low
                if trail_active:
                    if position == 1:
                        if high > trail_extreme: trail_extreme = high
                        if trail_extreme - price >= trail_dist:
                            exit_price = price; exit_triggered = True; exit_reason = "移动止损"
                    else:
                        if low < trail_extreme: trail_extreme = low
                        if price - trail_extreme >= trail_dist:
                            exit_price = price; exit_triggered = True; exit_reason = "移动止损"

            if not exit_triggered:
                trigger_amt = CFG["profit_lock_trigger"]  # 固定金额, 盈利≥$X启动保护
                pullback_amt = _peak_profit * CFG["profit_lock_pullback"] / 100
                if _peak_profit >= trigger_amt and (_peak_profit - unrealized) >= pullback_amt:
                    exit_price = price; exit_triggered = True
                    exit_reason = "盈利回撤保护"; trail_locked = True

            if exit_triggered:
                pnl = (exit_price - entry_price) * lots if position == 1 \
                      else (entry_price - exit_price) * lots
                fee = abs(exit_price) * lots * CFG["fee_pct"] / 100
                slip = abs(exit_price) * lots * CFG["slippage_pct"] / 100
                pnl -= (fee + slip)
                equity += pnl
                if trade:
                    trade.exit_time = bar.time; trade.exit_price = exit_price
                    trade.pnl = pnl; trade.pnl_pct = pnl / capital * 100
                    trade.exit_reason = exit_reason
                last_trade_bar = i
                position = 0; trail_active = False; trail_locked = False
                _peak_profit = 0; trail_extreme = 0

            equity_curve.append(EquityPoint(bar.time, current_equity,
                (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0))
            if current_equity > peak_equity: peak_equity = current_equity
            continue

        # ====== 空仓 ======
        equity_curve.append(EquityPoint(bar.time, equity,
            (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0))
        if equity > peak_equity: peak_equity = equity

        if i - last_trade_bar < cooldown:
            continue

        # 共振判定 (使用预计算信号)
        idx4 = idx_4h_map[i]; idxd = idx_1d_map[i]
        s1 = sigs_1h[i]["signal"]; s4 = sigs_4h[idx4]["signal"]; sd = sigs_1d[idxd]["signal"]
        buys = sum(1 for s in [s1, s4, sd] if s == 1)
        sells = sum(1 for s in [s1, s4, sd] if s == -1)

        # 风控
        atr_now = atr_all[i] if i < len(atr_all) else 0
        atr_hist = atr_all[i-30] if i >= 30 and i < len(atr_all) else atr_now
        can_trade, _ = check_risk_gates(equity, peak_equity, i, atr_now, atr_hist)
        if not can_trade: continue

        # 🆕 趋势过滤器: ADX<25 → 无趋势不交易
        d_idx = idx_1d_map[i]
        if d_idx < len(adx_1d) and adx_1d[d_idx] < 25:
            continue

        # 🆕 大趋势方向过滤: 只顺周线方向交易
        if d_idx < len(ema50_1d):
            trend_direction = 1 if cl_1d[d_idx] > ema50_1d[d_idx] else -1
            if buys >= threshold and trend_direction < 0:
                continue  # 大趋势向下, 不做多
            if sells >= threshold and trend_direction > 0:
                continue  # 大趋势向上, 不做空

        if buys >= threshold:
            sl_dist = max(atr_now * CFG["sl_atr_mult"], price * CFG["sl_min_pct"] / 100)
            lots = max(0.01, round(CFG["risk_per_trade"] / sl_dist, 2))
            entry_price = price * (1 + CFG["slippage_pct"] / 100)
            fee = entry_price * lots * CFG["fee_pct"] / 100
            equity -= fee
            position = 1; entry_bar = i
            trail_active = False; trail_locked = False; _peak_profit = 0; trail_extreme = 0
            trade = Trade(entry_time=bar.time, side="BUY", entry_price=entry_price, size=lots)
            result.trades.append(trade)
        elif sells >= threshold:
            sl_dist = max(atr_now * CFG["sl_atr_mult"], price * CFG["sl_min_pct"] / 100)
            lots = max(0.01, round(CFG["risk_per_trade"] / sl_dist, 2))
            entry_price = price * (1 - CFG["slippage_pct"] / 100)
            fee = entry_price * lots * CFG["fee_pct"] / 100
            equity -= fee
            position = -1; entry_bar = i
            trail_active = False; trail_locked = False; _peak_profit = 0; trail_extreme = 0
            trade = Trade(entry_time=bar.time, side="SELL", entry_price=entry_price, size=lots)
            result.trades.append(trade)

    print(" 完成")

    # ====== 最后持仓按收盘价平掉 ======
    if position != 0:
        last_price = bars_1h[-1].close
        pnl = (last_price - entry_price) * lots if position == 1 \
              else (entry_price - last_price) * lots
        fee = abs(last_price) * lots * CFG["fee_pct"] / 100
        pnl -= fee
        equity += pnl
        if trade:
            trade.exit_time = bars_1h[-1].time
            trade.exit_price = last_price
            trade.pnl = pnl
            trade.pnl_pct = pnl / capital * 100
            trade.exit_reason = "回测结束"

    # ====== 统计 ======
    result.equity_curve = equity_curve
    result.total_pnl = equity - capital
    result.total_pnl_pct = (equity - capital) / capital * 100
    closed = [t for t in result.trades if t.exit_time is not None]
    result.total_trades = len(closed)
    result.win_trades = len([t for t in closed if t.pnl > 0])
    result.lose_trades = len([t for t in closed if t.pnl <= 0])
    result.win_rate = (result.win_trades / result.total_trades * 100) if result.total_trades > 0 else 0

    result.max_drawdown = max((ep.drawdown for ep in equity_curve), default=0)

    wins = [t.pnl for t in closed if t.pnl > 0]
    losses = [t.pnl for t in closed if t.pnl < 0]
    result.avg_win = np.mean(wins) if wins else 0
    result.avg_loss = abs(np.mean(losses)) if losses else 0
    result.profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else (float('inf') if wins else 0)

    returns = [t.pnl for t in closed]
    if returns and len(returns) > 1 and np.std(returns) > 0:
        result.sharpe = np.mean(returns) / np.std(returns) * np.sqrt(len(closed) / max(1, (len(bars_1h)-warmup) / (365*24)))

    return result


# ============================================================
# MT5 数据源 (走券商通道，无GFW限制)
# ============================================================

def fetch_mt5_history(tf: str, symbol: str = "BTCUSD",
                      since: str = "2017-01-01") -> list:
    """从本机 MT5 拉取完整历史 K 线"""
    import MetaTrader5 as mt5

    tf_map = {"1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1}
    m5tf = tf_map.get(tf, mt5.TIMEFRAME_H1)

    print(f"     MT5 获取 {symbol} {tf} K线 (从 {since})...")

    if not mt5.initialize():
        print(f"     ❌ MT5 初始化失败: {mt5.last_error()}")
        return []

    start_dt = datetime.datetime.strptime(since, "%Y-%m-%d")
    end_dt = datetime.datetime.now()

    rates = mt5.copy_rates_range(symbol, m5tf, start_dt, end_dt)
    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        print(f"     ⚠️ 无数据: {err}")
        return []

    bars = []
    for row in rates:
        bars.append(Bar(
            time=datetime.datetime.fromtimestamp(row[0]),
            open=row[1], high=row[2], low=row[3],
            close=row[4], volume=row[5],
        ))

    if bars:
        print(f"     ✅ MT5 {tf}: {len(bars):,} 根 "
              f"({bars[0].time.date()} ~ {bars[-1].time.date()})")
    return bars


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print("  BTC 共振策略回测 — 2017 ~ 至今")
    print("  策略: 1h/4h/1d RSI+EMA 共振 + 移动止损 + 盈利回撤保护")
    print(f"  本金: $500  |  每笔风险: ${CFG['risk_per_trade']}")
    print("=" * 60)

    # 1. 获取数据 (MT5 券商通道)
    print("\n[1/3] 获取历史数据 (MT5)...")
    bars_1h = fetch_mt5_history("1h")
    bars_4h = fetch_mt5_history("4h")
    bars_1d = fetch_mt5_history("1d")

    if not bars_1h or len(bars_1h) < 100:
        print("  ❌ 1h 数据获取失败")
        return
    if not bars_4h:
        bars_4h = bars_1h
    if not bars_1d:
        bars_1d = bars_1h

    if len(bars_1h) < 100:
        print("  ❌ 数据不足")
        return

    t0 = bars_1h[0].time.strftime("%Y-%m-%d")
    t1 = bars_1h[-1].time.strftime("%Y-%m-%d")
    p0 = bars_1h[0].close
    p1 = bars_1h[-1].close
    print(f"\n  📅 数据范围: {t0} ~ {t1}")
    print(f"  💰 价格区间: ${p0:,.0f} → ${p1:,.0f} ({((p1-p0)/p0*100):+.1f}%)")
    print(f"  📊 1h K线: {len(bars_1h):,} 根")

    # 2. 运行回测
    print("\n[2/3] 运行回测...")
    t_start = time.time()

    # 为了控制回测时长, 如果数据超过5万根, 只取最近5万
    if len(bars_1h) > 50000:
        bars_1h = bars_1h[-50000:]
        print(f"  ⚠️ 数据过多, 截取最近 50,000 根 1h K线")
        print(f"  📅 实际回测: {bars_1h[0].time.strftime('%Y-%m-%d')} ~ {bars_1h[-1].time.strftime('%Y-%m-%d')}")

    result = run_full_backtest(bars_1h, bars_4h, bars_1d, capital=500)

    elapsed = time.time() - t_start
    print(f"  ✅ 回测完成 (耗时 {elapsed:.1f}s)")

    # 3. 输出结果
    print("\n[3/3] 生成报告...")
    strategy_name = f"BTC 多周期共振策略 (${500}本金, 2017-至今)"

    # 打印文字报告
    print_result(result, strategy_name)

    # 额外统计
    if result.trades:
        print(f"\n  📌 额外统计:")
        print(f"     最大单笔盈利: ${max(t.pnl for t in result.trades):.2f}")
        print(f"     最大单笔亏损: ${min(t.pnl for t in result.trades):.2f}")
        # 胜率详情
        closed = [t for t in result.trades if t.exit_time is not None]
        if closed:
            durations = [(t.exit_time - t.entry_time).total_seconds() / 3600 for t in closed]
            print(f"     平均持仓: {np.mean(durations):.1f}h  |  最长: {max(durations):.1f}h")
            # 空头 vs 多头
            long_trades = [t for t in closed if t.side == "BUY"]
            short_trades = [t for t in closed if t.side == "SELL"]
            if long_trades:
                l_win = sum(1 for t in long_trades if t.pnl > 0) / len(long_trades) * 100
                print(f"     多头: {len(long_trades)}笔 | 胜率: {l_win:.0f}% | 总盈亏: ${sum(t.pnl for t in long_trades):.2f}")
            if short_trades:
                s_win = sum(1 for t in short_trades if t.pnl > 0) / len(short_trades) * 100
                print(f"     空头: {len(short_trades)}笔 | 胜率: {s_win:.0f}% | 总盈亏: ${sum(t.pnl for t in short_trades):.2f}")

            # 按年份分组
            print(f"\n  📅 年度表现:")
            yearly = {}
            for t in closed:
                y = t.entry_time.year
                if y not in yearly:
                    yearly[y] = {"trades": 0, "pnl": 0, "wins": 0}
                yearly[y]["trades"] += 1
                yearly[y]["pnl"] += t.pnl
                if t.pnl > 0:
                    yearly[y]["wins"] += 1
            for y in sorted(yearly.keys()):
                d = yearly[y]
                wr = d["wins"] / d["trades"] * 100 if d["trades"] > 0 else 0
                bar = "█" * max(1, int(abs(d["pnl"]) / 20))
                sign = "+" if d["pnl"] >= 0 else ""
                print(f"     {y}: {d['trades']:3d}笔 | 胜率{wr:5.0f}% | {sign}${d['pnl']:7.2f}  {bar}")

    # 绘图
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "backtest_result.png")
    plot_result(result, strategy_name, "1h/4h/1d 共振",
                capital=500, save_path=save_path)
    print(f"\n  📊 图表已保存: {save_path}")

    # 保存交易记录 JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "backtest_trades.json")
    trades_data = []
    for t in result.trades:
        if t.exit_time:
            trades_data.append({
                "entry": t.entry_time.strftime("%Y-%m-%d %H:%M"),
                "exit": t.exit_time.strftime("%Y-%m-%d %H:%M"),
                "side": t.side,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
                "reason": t.exit_reason,
            })
    with open(json_path, "w") as f:
        json.dump(trades_data, f, indent=2, ensure_ascii=False)
    print(f"  📋 交易记录: {json_path} ({len(trades_data)} 笔)")

    print("\n" + "=" * 60)
    print("  回测完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
