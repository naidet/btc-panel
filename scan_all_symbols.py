"""扫描BTGT全部可交易品种"""
import sys
sys.path.insert(0, r"D:\BTC")
import MetaTrader5 as mt5

MT5_PATH = r"C:/Program Files/MetaTrader 5/terminal64.exe"

mt5.initialize(path=MT5_PATH, timeout=10000)
all_syms = mt5.symbols_get()

# 分类扫描
forex_major = []  # 主流外汇
forex_cross = []  # 交叉盘
metals = []       # 贵金属
indices = []      # 指数
crypto = []       # 加密货币
other = []

major_set = {"EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","NZDUSD","USDCAD"}

for s in all_syms:
    name = s.name
    if any(kw in name.upper() for kw in ["BTC","XBT","ETH","CRYPTO","BIT"]):
        crypto.append(s)
    elif any(kw in name.upper() for kw in ["XAU","XAG","GOLD","SILVER","XPT","XPD","PLAT","PALL"]):
        metals.append(s)
    elif name in major_set:
        forex_major.append(s)
    elif len(name) == 6 and name[3:] in ("USD","EUR","JPY","GBP","CHF","AUD","NZD","CAD"):
        forex_cross.append(s)
    elif any(kw in name.upper() for kw in ["US30","US100","SPX","NAS","DAX","UK100","JP225","HK50","AUS200","GER40","FRA40","STOXX","DOLLAR"]):
        indices.append(s)
    else:
        other.append(s)

print("=" * 60)
print("  BTGT 全部可交易品种")
print("=" * 60)

for cat, title, syms in [
    ("crypto", "🔵 加密货币", crypto),
    ("metals", "🟡 贵金属", metals),
    ("forex_major", "💱 主流外汇", forex_major),
    ("forex_cross", "💱 交叉盘", forex_cross),
    ("indices", "📊 指数", indices),
    ("other", "📦 其他", other),
]:
    if syms:
        print(f"\n{title} ({len(syms)}个):")
        for s in syms:
            # 测试报价
            mt5.symbol_select(s.name, True)
            tick = mt5.symbol_info_tick(s.name)
            if tick and tick.bid > 0:
                spread = tick.ask - tick.bid
                print(f"   ✅ {s.name:12s} | Bid={tick.bid:.4f} | 点差={spread:.4f} | "
                      f"point={s.point:.5f} | 最小手={s.volume_min}")
            else:
                print(f"   ⚠️  {s.name:12s} | (无报价/需订阅) | 最小手={s.volume_min}")

mt5.shutdown()
