#!/usr/bin/env python3
"""
MT5自动交易机器人 · 账户60107268 · $500
策略: RSI+EMA 日线, SL=1.5xATR, 策略反转出场(无追踪止盈)
"""
import sys, os, time, datetime, json, traceback
sys.path.insert(0, "D:/BTC")
os.chdir("D:/BTC")

import MetaTrader5 as mt5
from btc_trader import *

# 配置
SYMBOL = "BTCUSD"
MAGIC = 60107
RISK = 10.0      # 每笔风险 $10 (2% of $500)
SL_ATR = 1.5
INTERVAL = 1800  # 每30分钟检查一次
LOG = "mt5_auto_log.txt"
STATE_FILE = "mt5_auto_state.json"
MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

fetcher = DataFetcher()
strategy = RSI_EMA()
last_signal = 0  # 上次执行的信号

def log(msg):
    t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

def get_bars():
    for attempt in range(3):
        bars = fetcher.fetch_bars("1d", 80)
        if len(bars) >= 30:
            return bars
        log(f"数据不足({len(bars)}), 等待重试...")
        time.sleep(5)
    return []

def calc_params(bars):
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    atr = calc_atr(highs, lows, closes, 14)
    atr_v = atr[-1] if atr and atr[-1] > 0 else 800.0
    return closes[-1], atr_v

def get_lot(sl_price, entry_price):
    """计算手数: Risk = |entry - sl| * lot_size * contract_size / point_divider"""
    sl_dist = abs(entry_price - sl_price)
    if sl_dist < 1:
        return 0.01
    lot = RISK / sl_dist  # 因为1 lot = 1 BTCUSD
    lot = round(max(0.01, min(0.1, lot)), 2)
    return lot

def do_trade(action, entry_price, sl_price):
    """执行交易"""
    mt5.symbol_select(SYMBOL, True)
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        log(f"无法获取{SYMBOL}报价, 跳过交易")
        return False
    
    if action == "CLOSE":
        pos = mt5.positions_get(symbol=SYMBOL)
        if not pos: return True
        p = pos[0]
        close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if p.type == 0 else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
            "volume": p.volume, "type": close_type,
            "position": p.ticket, "price": close_price,
            "deviation": 50, "magic": MAGIC,
            "comment": "Close", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"平仓 #{p.ticket} 盈亏=${p.profit:.2f}")
            return True
        log(f"平仓失败: {getattr(r,'retcode','?')} {getattr(r,'comment','?')}")
        return False
    
    elif action in ["BUY", "SELL"]:
        is_buy = action == "BUY"
        price = tick.ask if is_buy else tick.bid
        lot = get_lot(sl_price, entry_price)
        if lot <= 0: lot = 0.01
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
            "volume": lot, "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": price, "sl": sl_price, "tp": 0,
            "deviation": 50, "magic": MAGIC,
            "comment": f"RSI_{action}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"开仓 {action} {lot:.2f}lot @${price:.2f} SL=${sl_price:.2f}")
            return True
        err = getattr(r, 'retcode', 'None')
        err_msg = getattr(r, 'comment', 'order_send returned None')
        log(f"开仓失败: retcode={err} ({err_msg})")
        return False
    
    return False

def auto_loop():
    global last_signal
    log("=" * 50)
    log(f"🚀 MT5自动交易启动 | 账户60107268 | RSI+EMA日线")
    log(f"   每笔风险${RISK} | SL={SL_ATR}×ATR | 每{INTERVAL//60}分钟检查")
    log("=" * 50)
    
    # 检查现有持仓
    mt5.symbol_select(SYMBOL, True)
    pos = mt5.positions_get(symbol=SYMBOL)
    if pos:
        p = pos[0]
        side = "BUY" if p.type == 0 else "SELL"
        log(f"检测到现有持仓: {side} {p.volume:.2f}lot @${p.price_open:.2f} 盈亏=${p.profit:.2f}")
    else:
        log("当前无持仓")
    mt5.shutdown()
    
    while True:
        try:
            # 连接MT5 (首次或断线重连)
            if not mt5.initialize(path=MT5_PATH):
                log(f"MT5初始化失败, 60s后重试...")
                time.sleep(60)
                continue
            mt5.symbol_select(SYMBOL, True)
            
            # 获取数据 → 计算信号
            bars = get_bars()
            if not bars:
                time.sleep(300)
                continue
            
            sig = strategy.on_data(bars)
            current = sig.signal  # 1=long, -1=short, 0=wait
            price, atr_v = calc_params(bars)
            sl_dist = atr_v * SL_ATR
            
            # 获取当前仓位
            mt5.symbol_select(SYMBOL, True)
            pos = mt5.positions_get(symbol=SYMBOL)
            has_pos = bool(pos and len(pos) > 0)
            
            log(f"行情: ${price:.0f} ATR=${atr_v:.0f} 信号={'🟢买入' if current==1 else '🔴卖出' if current==-1 else '⚪观望'}")
            
            # === 决策逻辑 ===
            if current != 0:
                sl_price = price - sl_dist if current == 1 else price + sl_dist
                
                if not has_pos:
                    # 无仓 → 直接开
                    if do_trade("BUY" if current == 1 else "SELL", price, sl_price):
                        last_signal = current
                elif current != last_signal:
                    # 信号变了 → 平旧开新
                    side = "BUY" if pos[0].type == 0 else "SELL"
                    log(f"信号变化: 上次={'BUY' if last_signal==1 else 'SELL' if last_signal==-1 else '无'} → 当前={'BUY' if current==1 else 'SELL'}")
                    do_trade("CLOSE", 0, 0)
                    do_trade("BUY" if current == 1 else "SELL", price, sl_price)
                    last_signal = current
                # else: 持仓方向不变, 持有
            else:
                # 信号=观望 → 有仓就平
                if has_pos:
                    log("信号转为观望, 平仓")
                    do_trade("CLOSE", 0, 0)
                last_signal = 0
            
            # 保持MT5连接不关闭
            # mt5.shutdown()  # 持续连接, 不关闭
            
        except Exception as e:
            log(f"异常: {e}\n{traceback.format_exc()}")
            try: mt5.shutdown()
            except: pass
        
        time.sleep(INTERVAL)

if __name__ == "__main__":
    # 先测试连接
    if not mt5.initialize(path=MT5_PATH):
        print("❌ MT5初始化失败")
        sys.exit(1)
    
    acc = mt5.account_info()
    if not acc:
        print("❌ 未登录MT5账户")
        mt5.shutdown()
        sys.exit(1)
    
    print(f"✅ 已连接 账户#{acc.login} 余额=${acc.balance:.2f}")
    
    if not mt5.symbol_select(SYMBOL, True):
        print(f"❌ 无法加载{SYMBOL}")
        mt5.shutdown()
        sys.exit(1)
    
    mt5.shutdown()
    auto_loop()
