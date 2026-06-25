#!/usr/bin/env python3
"""btc_panel 功能测试脚本"""
import sys, os
os.chdir('D:/BTC')
sys.path.insert(0, 'D:/BTC')
sys.path.insert(0, r'C:\Users\82682\.workbuddy\binaries\python\envs\default\Lib\site-packages')

print('=== 导入测试 ===')
import btc_panel
print('✅ btc_panel 导入成功')

print()
print('=== MT5 连接测试 ===')
ok = btc_panel.mt5_ensure()
print(f'MT5连接: {"✅ 成功" if ok else "❌ 失败"}')

if ok:
    print()
    print('=== 账户信息测试 ===')
    acct = btc_panel.get_mt5_account_info()
    if acct:
        print(f'  余额: {acct["balance"]:.2f}')
        print(f'  净值: {acct["equity"]:.2f}')
        print(f'  保证金: {acct["margin"]:.2f}')

    print()
    print('=== 当日盈亏测试 ===')
    daily = btc_panel.get_daily_pnl()
    print(f'  日期: {daily["date"]}')
    print(f'  起始余额: {daily["start_balance"]}')
    print(f'  当前盈亏: ${daily["pnl"]:.2f}')

    print()
    print('=== 持仓查询测试 ===')
    for sym in ['BTCUSD', 'XAUUSD']:
        positions = btc_panel.get_mt5_positions(sym)
        print(f'  {sym}: {len(positions)} 个持仓')
        for p in positions:
            side = '多' if p.type == 0 else '空'
            print(f'    {side}仓 手数:{p.volume} 盈亏:${p.profit:.2f}')

    print()
    print('=== 信号计算测试 (BTCUSD) ===')
    res = btc_panel.calc_resonance('BTCUSD', btc_panel.DEFAULT_PARAMS)
    if res:
        for r in res:
            sig = '看多' if r['signal'] == 1 else ('看空' if r['signal'] == -1 else '观望')
            print(f'  {r["timeframe"]}: {sig} (强度:{r["strength"]})')
    else:
        print('  无数据')

    print()
    print('=== 风控闸门测试 ===')
    passed, reason = btc_panel.check_risk_gates('BTCUSD', 'BUY', btc_panel.DEFAULT_PARAMS)
    print(f'  开多风控: {"✅ 通过" if passed else "❌ 拒绝"} ({reason})')
    passed, reason = btc_panel.check_risk_gates('BTCUSD', 'SELL', btc_panel.DEFAULT_PARAMS)
    print(f'  开空风控: {"✅ 通过" if passed else "❌ 拒绝"} ({reason})')

print()
print('=== 测试完成 ===')
