#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整检查账户状态"""
import sys, os
os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")
import MetaTrader5 as mt5
from datetime import datetime, timedelta

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=MT5_PATH):
    print("MT5连接失败")
    sys.exit(1)

print("=" * 60)
print("账户状态")
print("=" * 60)
acct = mt5.account_info()
if acct:
    print(f"余额: {acct.balance:.2f}")
    print(f"净值: {acct.equity:.2f}")
    print(f"保证金: {acct.margin:.2f}")
    print(f"可用: {acct.margin_free:.2f}")

print()
print("=" * 60)
print("当前持仓")
print("=" * 60)
positions = mt5.positions_get()
if positions:
    total_profit = 0.0
    for p in positions:
        side = "多" if p.type == 0 else "空"
        profit = p.profit
        total_profit += profit
        print(f"{p.symbol} {side}仓  手数:{p.volume}  开仓:{p.price_open:.2f}  现价:{p.price_current:.2f}  盈亏:${profit:.2f}")
    print(f"\n持仓总浮动盈亏: ${total_profit:.2f}")
else:
    print("无持仓")

print()
print("=" * 60)
print("今日已平仓交易盈亏")
print("=" * 60)
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
now = datetime.now()
deals = mt5.history_deals_get(today, now)
if deals:
    today_profit = 0.0
    for d in deals:
        today_profit += d.profit
    print(f"今日平仓总盈亏: ${today_profit:.2f}")
    print(f"平仓笔数: {len(deals)}")
    print("\n最近10笔平仓:")
    import time
    for d in deals[-10:]:
        deal_type = "买" if d.type == 0 else "卖" if d.type == 1 else "其他"
        # time_msc 是毫秒时间戳
        t = datetime.fromtimestamp(d.time_msc / 1000)
        print(f"  {t.strftime('%H:%M')} {d.symbol} {deal_type} 手数:{d.volume:.2f} 价格:{d.price:.2f} 盈亏:${d.profit:.2f}")
else:
    print("今日无平仓交易")

mt5.shutdown()
print("\n" + "=" * 60)
