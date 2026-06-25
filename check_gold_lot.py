#!/usr/bin/env python3
"""查看黄金当前持仓手数"""
import sys, os
os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

import MetaTrader5 as mt5

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

print("=" * 50)
print("查看黄金持仓")
print("=" * 50)

if not mt5.initialize(path=MT5_PATH):
    print(f"❌ MT5初始化失败: {mt5.last_error()}")
    sys.exit(1)

print("✅ MT5连接成功\n")

# 查看黄金持仓
positions = mt5.positions_get(symbol="XAUUSD")
if positions:
    print(f"📊 黄金持仓 ({len(positions)}个):")
    print("-" * 40)
    for p in positions:
        side = "多" if p.type == 0 else "空"
        print(f"  {p.symbol} {side}仓")
        print(f"    手数: {p.volume}")
        print(f"    开仓价: {p.price_open:.2f}")
        print(f"    当前价: {p.price_current:.2f}")
        print(f"    止损: {p.sl:.2f}")
        print(f"    止盈: {p.tp:.2f}")
        print(f"    盈亏: ${p.profit:.2f}")
        print(f"    魔术号: {p.magic}")
        print()
else:
    print("📊 当前无黄金持仓\n")

# 查看面板参数里的固定手数设置
import json
try:
    params = json.load(open("panel_params.json"))
    lot_fixed = params.get("lot_fixed", 0)
    print(f"⚙️ 面板参数设置:")
    print(f"  固定手数(lot_fixed): {lot_fixed}")
    if lot_fixed > 0:
        print(f"  ⚠️ 注意: 固定手数已启用，开仓将按{lot_fixed}手")
    else:
        print(f"  ℹ️ 固定手数未启用，按风险自动计算")
except Exception as e:
    print(f"⚙️ 读取参数失败: {e}")

mt5.shutdown()
print("\n" + "=" * 50)