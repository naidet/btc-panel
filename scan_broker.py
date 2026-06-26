"""扫描当前MT5券商数据"""
import sys
sys.path.insert(0, r"D:\BTC")
import MetaTrader5 as mt5

MT5_PATH = r"C:/Program Files/MetaTrader 5/terminal64.exe"

print("=" * 60)
print("  券商数据扫描")
print("=" * 60)

# 1. 初始化
if not mt5.initialize(path=MT5_PATH, timeout=10000):
    print("❌ MT5初始化失败")
    input("按回车退出...")
    sys.exit(1)

print("✅ MT5已连接")

# 2. 账号信息
acct = mt5.account_info()
if acct:
    print(f"\n📊 账号信息:")
    print(f"   账号: {acct.login}")
    print(f"   服务器: {acct.server}")
    print(f"   券商: {acct.company}")
    print(f"   余额: ${acct.balance:,.2f}")
    print(f"   净值: ${acct.equity:,.2f}")
    print(f"   杠杆: 1:{acct.leverage}")
    print(f"   货币: {acct.currency}")

# 3. 扫描目标品种
targets = ["BTCUSD", "BTC", "XAUUSD", "GOLD", "XAGUSD", "SILVER"]
print(f"\n📋 品种扫描:")

# 先看所有包含BTC和XAU/USD相关符号
all_symbols = mt5.symbols_get()
btc_candidates = []
gold_candidates = []
silver_candidates = []

if all_symbols:
    total = len(all_symbols)
    print(f"   总品种数: {total}")
    
    for s in all_symbols:
        name = s.name.upper()
        if any(kw in name for kw in ["BTC", "XBT", "BIT"]):
            btc_candidates.append(s)
        if any(kw in name for kw in ["XAU", "GOLD", "AU"]):
            gold_candidates.append(s)
        if any(kw in name for kw in ["XAG", "SILVER", "AG"]):
            silver_candidates.append(s)

print(f"\n🔵 BTC候选 ({len(btc_candidates)}个):")
for s in btc_candidates:
    print(f"   {s.name:20s} | digits={s.digits} | point={s.point:.5f} | "
          f"trade_mode={s.trade_mode} | 最小手={s.volume_min} | "
          f"步长={s.volume_step}")

print(f"\n🟡 黄金候选 ({len(gold_candidates)}个):")
for s in gold_candidates:
    print(f"   {s.name:20s} | digits={s.digits} | point={s.point:.5f} | "
          f"trade_mode={s.trade_mode} | 最小手={s.volume_min} | "
          f"步长={s.volume_step}")

print(f"\n⚪ 白银候选 ({len(silver_candidates)}个):")
for s in silver_candidates:
    print(f"   {s.name:20s} | digits={s.digits} | point={s.point:.5f} | "
          f"trade_mode={s.trade_mode} | 最小手={s.volume_min} | "
          f"步长={s.volume_step}")

# 4. 报价测试
print(f"\n💰 报价测试:")
for sym in ["BTCUSD", "XAUUSD", "XAGUSD"] + [s.name for s in btc_candidates[:1] + gold_candidates[:1] + silver_candidates[:1]]:
    try:
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        if tick:
            spread = (tick.ask - tick.bid) if tick.ask and tick.bid else 0
            print(f"   {sym:20s} | Bid={tick.bid:.2f} | Ask={tick.ask:.2f} | 点差={spread:.2f}")
        else:
            print(f"   {sym:20s} | ⚠ 无报价")
    except Exception as e:
        print(f"   {sym:20s} | ❌ {e}")

# 5. 持仓检查
positions = mt5.positions_get()
if positions:
    print(f"\n📈 当前持仓 ({len(positions)}个):")
    for p in positions:
        side = "多" if p.type == 0 else "空"
        print(f"   {p.symbol:12s} {side} | 入场${p.price_open:.2f} | "
              f"手数{p.volume} | 盈亏${p.profit:.2f}")
else:
    print(f"\n📈 当前持仓: 无")

mt5.shutdown()
print(f"\n✅ 扫描完成")
