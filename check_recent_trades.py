#!/usr/bin/env python3
"""检查最近的交易"""
import sys, os, time
os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

import MetaTrader5 as mt5
from datetime import datetime, timedelta

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

print("=" * 50)
print("检查最近的交易活动")
print("=" * 50)

if not mt5.initialize(path=MT5_PATH):
    print(f"❌ MT5初始化失败: {mt5.last_error()}")
    sys.exit(1)

print("✅ MT5连接成功\n")

# 检查所有持仓
positions = mt5.positions_get()
if positions:
    print(f"📊 当前持仓 ({len(positions)}个):")
    print("-" * 40)
    for p in positions:
        side = "多" if p.type == 0 else "空"
        current_price = p.price_open + (p.profit / p.volume) if p.volume > 0 else 0
        print(f"  {p.symbol} {side}仓")
        print(f"    手数: {p.volume:.2f}")
        print(f"    开仓价: {p.price_open:.2f}")
        print(f"    当前价: {current_price:.2f}")
        print(f"    止损: {p.sl:.2f}")
        print(f"    止盈: {p.tp:.2f}")
        print(f"    盈亏: ${p.profit:.2f}")
        print(f"    魔术号: {p.magic} (面板开的仓是60107)")
        print()
else:
    print("📊 当前无持仓\n")

# 检查最近20分钟的成交
now = datetime.now()
from_time = now - timedelta(minutes=20)
deals = mt5.history_deals_get(from_time, now)

if deals:
    print(f"📈 最近20分钟的成交 ({len(deals)}笔):")
    print("-" * 40)
    for d in deals[-10:]:  # 显示最近10笔
        deal_type = "买" if d.type == 0 else "卖" if d.type == 1 else "其他"
        print(f"  {d.time_msc.strftime('%H:%M:%S')} {d.symbol} {deal_type}")
        print(f"    手数: {d.volume:.2f}  价格: {d.price:.2f}")
        print(f"    盈亏: ${d.profit:.2f}  魔术号: {d.magic}")
        print()
else:
    print("📈 最近20分钟无成交\n")

# 检查今天的盈亏
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
today_deals = mt5.history_deals_get(today, now)
if today_deals:
    total_profit = sum(d.profit for d in today_deals)
    print(f"💰 今天总盈亏: ${total_profit:.2f}")
else:
    print("💰 今天无交易")

mt5.shutdown()
print("\n" + "=" * 50)