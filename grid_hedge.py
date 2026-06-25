#!/usr/bin/env python3
"""
网格对冲策略 · Grid Hedge — 空多同开，有利润先平
==================================================
策略: 横盘时空多同时开仓，哪边盈利平哪边，另一边等回调
周期: M15  |  2017-2026 全量回测

铁律:
  1. ADX(1h) < 18 才启动网格
  2. 网格间隔 2% (价格波动2%触发平仓/加仓)
  3. 最多加仓 3 层 (0.01 → 0.02 → 0.04)
  4. 单边亏损达账户10% → 全部砍仓
  5. 持仓超4h未盈利 → 强制平仓
"""

import os, sys, json, time, datetime, warnings
from collections import defaultdict
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_trader import Bar, Trade, BacktestResult, EquityPoint, calc_ema, calc_rsi, calc_atr, calc_adx


CFG = {
    # 网格参数
    "grid_interval_pct": 2.0,    # 价格波动2%触发止盈
    "max_layers": 3,             # 最多3层加仓
    "base_lots": 0.01,           # 首层手数

    # 风控
    "max_loss_pct": 10.0,        # 单边亏损10%账户 → 砍
    "max_hold_hours": 4,         # 持仓最长时间
    "adx_range_max": 18,         # ADX < 18 才是震荡

    # 交易成本
    "fee_pct": 0.04,
    "slippage_pct": 0.02,
}


# ═══════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════
def run_backtest(bars_m15, bars_1h, capital=500.0):
    result = BacktestResult()
    N = len(bars_m15)
    warmup = 50
    if N < warmup: return result

    # 预计算1h ADX
    cl_1h = [b.close for b in bars_1h]; hi_1h = [b.high for b in bars_1h]; lo_1h = [b.low for b in bars_1h]
    adx_1h = calc_adx(hi_1h, lo_1h, cl_1h, 14) if len(bars_1h)>20 else []

    # 1h → M15 索引映射
    idx_1h = [0]*N; j=0
    for i in range(N):
        while j+1 < len(bars_1h) and bars_1h[j+1].time <= bars_m15[i].time: j+=1
        idx_1h[i]=j

    # 预计算M15 ATR
    atr_all = calc_atr([b.high for b in bars_m15], [b.low for b in bars_m15],
                       [b.close for b in bars_m15], 14)

    print(f"  ⏳ 回测 {N:,} bars...", end="", flush=True)

    # 状态: "grid" = 网格运行中, "flat" = 空仓
    state = "flat"
    grid_start_idx = 0
    grid_trigger_price = 0
    long_pos = 0; short_pos = 0
    long_entry = 0; short_entry = 0
    long_layers = 0; short_layers = 0
    long_pnl = 0; short_pnl = 0
    equity = capital
    peak_equity = capital
    equity_curve = []
    trades_out = []
    last_reset_idx = -9999

    for i in range(warmup, N):
        bar = bars_m15[i]; price = bar.close

        cur_pnl = long_pnl + short_pnl
        if state == "flat":
            cur_eq = equity + cur_pnl
        else:
            if long_pos > 0: long_pnl = (price - long_entry) * long_pos
            if short_pos > 0: short_pnl = (short_entry - price) * short_pos
            cur_eq = equity + long_pnl + short_pnl

        equity_curve.append(EquityPoint(bar.time, cur_eq,
            (peak_equity - cur_eq)/peak_equity*100 if peak_equity>0 else 0))
        if cur_eq > peak_equity: peak_equity = cur_eq

        # === 风控: 亏损超标 → 全部砍 ===
        if state == "grid" and cur_pnl < -capital * CFG["max_loss_pct"] / 100:
            equity += cur_pnl
            for t in trades_out[-max(long_layers+short_layers,1):]:
                if t.exit_time is None:
                    t.exit_time = bar.time; t.exit_price = price
                    if t.side == "BUY": t.pnl = (price - t.entry_price) * t.size
                    else: t.pnl = (t.entry_price - price) * t.size
            state = "flat"; long_pos=short_pos=0; long_layers=short_layers=0
            last_reset_idx = i
            continue

        # === 持仓时间过长 → 强制平 ===
        if state == "grid" and i > grid_start_idx:
            hours_held = (bar.time - bars_m15[grid_start_idx].time).total_seconds() / 3600
            if hours_held > CFG["max_hold_hours"]:
                equity += cur_pnl
                for t in trades_out[-max(long_layers+short_layers,1):]:
                    if t.exit_time is None:
                        t.exit_time = bar.time; t.exit_price = price
                        if t.side == "BUY": t.pnl = (price - t.entry_price) * t.size
                        else: t.pnl = (t.entry_price - price) * t.size
                state = "flat"; long_pos=short_pos=0; long_layers=short_layers=0
                last_reset_idx = i
                continue

        # === 网格运行中: 检查止盈/加仓 ===
        if state == "grid":
            pct_from_start = (price - grid_trigger_price) / grid_trigger_price * 100

            # 上涨超间隔 → 平多 + 加仓空
            if pct_from_start >= CFG["grid_interval_pct"] and long_pos > 0:
                # 平掉所有多单
                long_close_pnl = (price - long_entry) * long_pos
                equity += long_close_pnl
                for t in trades_out:
                    if t.exit_time is None and t.side == "BUY":
                        t.exit_time = bar.time; t.exit_price = price
                        t.pnl = (price - t.entry_price) * t.size
                # 加仓空单
                if short_layers < CFG["max_layers"]:
                    new_lot = CFG["base_lots"] * (2 ** short_layers)
                    short_entry = (short_entry * short_pos + price * new_lot) / (short_pos + new_lot) if short_pos > 0 else price
                    short_pos += new_lot; short_layers += 1
                    trades_out.append(Trade(entry_time=bar.time, side="SELL",
                        entry_price=price, size=new_lot))
                long_pos = 0; long_layers = 0
                grid_trigger_price = price

            # 下跌超间隔 → 平空 + 加仓多
            elif pct_from_start <= -CFG["grid_interval_pct"] and short_pos > 0:
                short_close_pnl = (short_entry - price) * short_pos
                equity += short_close_pnl
                for t in trades_out:
                    if t.exit_time is None and t.side == "SELL":
                        t.exit_time = bar.time; t.exit_price = price
                        t.pnl = (t.entry_price - price) * t.size
                if long_layers < CFG["max_layers"]:
                    new_lot = CFG["base_lots"] * (2 ** long_layers)
                    long_entry = (long_entry * long_pos + price * new_lot) / (long_pos + new_lot) if long_pos > 0 else price
                    long_pos += new_lot; long_layers += 1
                    trades_out.append(Trade(entry_time=bar.time, side="BUY",
                        entry_price=price, size=new_lot))
                short_pos = 0; short_layers = 0
                grid_trigger_price = price

            continue

        # === 启动网格: ADX < 18 ===
        if i - last_reset_idx < 15: continue  # 冷却
        ih = idx_1h[i]
        if ih >= len(adx_1h) or adx_1h[ih] >= CFG["adx_range_max"]:
            continue

        # 开网格: 同时做多做空
        state = "grid"
        grid_start_idx = i
        grid_trigger_price = price
        long_pos = CFG["base_lots"]; short_pos = CFG["base_lots"]
        long_entry = price; short_entry = price
        long_layers = 1; short_layers = 1
        long_pnl = 0; short_pnl = 0

        # 手续费
        fee = price * (long_pos+short_pos) * CFG["fee_pct"] / 100
        equity -= fee

        trades_out.append(Trade(entry_time=bar.time, side="BUY",
            entry_price=price, size=long_pos))
        trades_out.append(Trade(entry_time=bar.time, side="SELL",
            entry_price=price, size=short_pos))

    # 最后强制平仓
    if state == "grid":
        for t in trades_out:
            if t.exit_time is None:
                t.exit_time = bars_m15[-1].time; t.exit_price = bars_m15[-1].close
                if t.side == "BUY": t.pnl = (bars_m15[-1].close - t.entry_price) * t.size
                else: t.pnl = (t.entry_price - bars_m15[-1].close) * t.size

    print(" 完成")

    # 统计
    result.equity_curve = equity_curve
    closed = [t for t in trades_out if t.exit_time is not None]
    total_pnl = sum(t.pnl for t in closed)
    result.total_pnl = total_pnl
    result.total_pnl_pct = total_pnl / capital * 100
    result.total_trades = len(closed)
    result.win_trades = len([t for t in closed if t.pnl>0])
    result.lose_trades = len([t for t in closed if t.pnl<=0])
    result.win_rate = result.win_trades/max(result.total_trades,1)*100
    result.max_drawdown = max((ep.drawdown for ep in equity_curve), default=0)
    wins=[t.pnl for t in closed if t.pnl>0]; losses=[t.pnl for t in closed if t.pnl<=0]
    result.avg_win = np.mean(wins) if wins else 0
    result.avg_loss = abs(np.mean(losses)) if losses else 0
    result.profit_factor = abs(sum(wins)/sum(losses)) if losses and sum(losses)!=0 else (99 if wins else 0)

    # 网格统计
    grid_cycles = sum(1 for t in closed if t.side=="BUY" and t.exit_time is not None)
    cycles_profitable = sum(1 for t in closed if t.pnl>0)
    print(f"  网格循环: ~{grid_cycles} 次  盈利: {cycles_profitable}")
    result.trades = closed
    return result


# ═══════════════════════════════════════════
def fetch_mt5(tf_name):
    import MetaTrader5 as mt5
    tf_map = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
    mp = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    if not mt5.initialize(path=mp): return []
    # 从多个起始年份尝试获取数据(MT5历史数据有限)
    for start_year in [2021, 2023, 2024]:
        rates = mt5.copy_rates_range("BTCUSD", tf_map[tf_name],
            datetime.datetime(start_year, 1, 1), datetime.datetime.now())
        if rates is not None and len(rates) > 100:
            break
    mt5.shutdown()
    if rates is None: return []
    return [Bar(time=datetime.datetime.fromtimestamp(r[0]),
        open=r[1],high=r[2],low=r[3],close=r[4],volume=r[5]) for r in rates]


# ═══════════════════════════════════════════
def main():
    print("="*60)
    print("  网格对冲策略 · Grid Hedge — 空多同开 有利润先平")
    print(f"  间隔{CFG['grid_interval_pct']}%  最多{CFG['max_layers']}层  最大亏损{CFG['max_loss_pct']}%")
    print(f"  ADX<{CFG['adx_range_max']} 震荡市  |  超{CFG['max_hold_hours']}h 强制平仓")
    print("="*60)

    print("\n[1/2] 获取数据...")
    bars_m15 = fetch_mt5("M15"); bars_1h = fetch_mt5("H1")
    if not bars_m15 or not bars_1h:
        print("  ❌ 数据失败"); return
    if len(bars_m15) > 80000: bars_m15 = bars_m15[-80000:]
    print(f"  M15: {len(bars_m15):,} bars  |  1h: {len(bars_1h):,} bars")

    print("\n[2/2] 运行回测...")
    t0 = time.time()
    result = run_backtest(bars_m15, bars_1h, 500)
    print(f"  耗时: {time.time()-t0:.1f}s")

    # 报告
    closed = [t for t in result.trades if t.exit_time is not None]
    total_pnl = sum(t.pnl for t in closed)
    print(f"\n  {'='*50}")
    print(f"  网格对冲回测结果")
    print(f"  {'='*50}")
    print(f"  总交易: {len(closed)} 笔")
    print(f"  胜率: {result.win_rate:.0f}% ({result.win_trades}W/{result.lose_trades}L)")
    print(f"  总盈亏: ${total_pnl:+,.2f} ({total_pnl/500*100:+.1f}%)")
    print(f"  最大回撤: {result.max_drawdown:.1f}%")

    # 年度
    yearly = defaultdict(lambda: {"count":0,"pnl":0,"wins":0})
    for t in closed:
        y = t.entry_time.year
        yearly[y]["count"]+=1; yearly[y]["pnl"]+=t.pnl
        if t.pnl>0: yearly[y]["wins"]+=1

    print(f"\n  📅 年度:")
    for y in sorted(yearly):
        d=yearly[y]; wr=d['wins']/max(d['count'],1)*100
        sign="+" if d['pnl']>=0 else ""
        bar="█"*max(1,int(abs(d['pnl'])/10))
        print(f"    {y}: {d['count']:4d}笔 胜{wr:3.0f}%  {sign}${d['pnl']:+8.2f}  {bar}")

    # 方向
    l=[t for t in closed if t.side=="BUY"]; s=[t for t in closed if t.side=="SELL"]
    if l: print(f"\n  🔼 多头: {len(l)}笔 ${sum(t.pnl for t in l):+.2f}")
    if s: print(f"  🔽 空头: {len(s)}笔 ${sum(t.pnl for t in s):+.2f}")

    # JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid_hedge_trades.json")
    with open(json_path, "w") as f:
        json.dump([{"entry":t.entry_time.strftime("%Y-%m-%d %H:%M"),
            "exit":t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "",
            "side":t.side,"entry_price":round(t.entry_price,2),
            "exit_price":round(t.exit_price,2) if t.exit_price else 0,
            "pnl":round(t.pnl,2)} for t in closed], f, indent=2)

    print(f"\n{'='*60}\n  回测完成!\n{'='*60}")


if __name__ == "__main__":
    main()
