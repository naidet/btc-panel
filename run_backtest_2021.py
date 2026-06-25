"""策略回测: 2021.6至今, 本金$10K, 当前策略模拟"""
import numpy as np, json, warnings
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta
import MetaTrader5 as mt5

CAPITAL = 10000.0
MT5_PATH = 'C:/Program Files/MetaTrader 5/terminal64.exe'

def calc_ema(cl, period):
    k=2.0/(period+1)
    e=[float(cl[0])]
    for v in cl[1:]: e.append(v*k+e[-1]*(1-k))
    return e

def calc_rsi(cl, period=14):
    n=len(cl)
    if n<period+1: return [50.0]*n
    r=[np.nan]*period
    d=list(np.diff(cl[:period+1]))
    g=sum(x for x in d if x>0)/period
    l=sum(-x for x in d if x<0)/period
    r.append(100-100/(1+g/(l+0.0001)))
    for i in range(period+1,n):
        de=cl[i]-cl[i-1]
        g=g*(period-1)/period+(de if de>0 else 0)/period
        l=l*(period-1)/period+(-de if de<0 else 0)/period
        r.append(100-100/(1+g/(l+0.0001)))
    return r

def calc_adx(hi,lo,cl,period=14):
    n=len(hi)
    if n<period*2: return [0.0]*n
    tr,pdm,mdm=[0.0]*n,[0.0]*n,[0.0]*n
    for i in range(1,n):
        tr[i]=max(hi[i]-lo[i],abs(hi[i]-cl[i-1]),abs(lo[i]-cl[i-1]))
        pdm[i]=max(hi[i]-hi[i-1],0) if hi[i]-hi[i-1]>lo[i-1]-lo[i] else 0
        mdm[i]=max(lo[i-1]-lo[i],0) if lo[i-1]-lo[i]>hi[i]-hi[i-1] else 0
    atr=[sum(tr[1:period+1])/period]*period+[0.0]*(n-period)
    pdi,mdi=[0.0]*period+[0.0]*(n-period),[0.0]*period+[0.0]*(n-period)
    adx=[0.0]*period+[0.0]*(n-period)
    for i in range(period,n):
        atr[i]=(atr[i-1]*(period-1)+tr[i])/period
        pdi[i]=(pdi[i-1]*(period-1)+pdm[i])/period if atr[i]>0 else 0
        mdi[i]=(mdi[i-1]*(period-1)+mdm[i])/period if atr[i]>0 else 0
        dx=abs(pdi[i]-mdi[i])/(pdi[i]+mdi[i]+0.0001)*100
        if i>=period*2-1: adx[i]=(adx[i-1]*(period-1)+dx)/period
    return adx

print('='*60)
print('  BTC策略回测: 2021.06 ~ 现在')
print(f'  本金: ${CAPITAL:,.0f}')
print('='*60)

# ===== 1. 拉数据 =====
mt5.initialize(path=MT5_PATH)
mt5.symbol_select('BTCUSD',True)

# 4h: 主力信号周期
r4h=mt5.copy_rates_range('BTCUSD',mt5.TIMEFRAME_H4, datetime(2021,4,1), datetime.now())
if r4h is None or len(r4h)<200: print('4h数据不足'); exit(1)

c4=np.array([r[4] for r in r4h],float); h4=np.array([r[2] for r in r4h],float)
l4=np.array([r[3] for r in r4h],float)
t4=[datetime.fromtimestamp(r[0]) for r in r4h]

# 1h: 辅助确认
r1h=mt5.copy_rates_range('BTCUSD',mt5.TIMEFRAME_H1, datetime(2021,4,1), datetime.now())
mt5.shutdown()

c1=np.array([r[4] for r in r1h],float) if r1h is not None else np.array([])
t1=[datetime.fromtimestamp(r[0]) for r in r1h] if r1h is not None else []
print(f'4h: {len(c4)}根  {t4[0]} ~ {t4[-1]}')
print(f'1h: {len(c1)}根')

# ===== 2. 过滤到2021-06开始 =====
start_idx=0
for i,t in enumerate(t4):
    if t>=datetime(2021,6,1): start_idx=i; break

c4=c4[start_idx:]; h4=h4[start_idx:]; l4=l4[start_idx:]; t4=t4[start_idx:]
print(f'回测开始: {t4[0]} 价格=${c4[0]:,.0f}')

# ===== 3. 策略参数(BTC默认) =====
EMA_P=20; RSI_P=14
RSI_LONG_LO=50; RSI_LONG_HI=70
RSI_SHORT_LO=30; RSI_SHORT_HI=50
RES_THRESH=3
SL_ATR_MULT=1.5; SL_MIN=800
TRAIL_PROFIT=3; TRAIL_DIST=200
RISK_PER_TRADE=200  # $200 risk per trade = 2% of $10K

n=len(c4)

# ===== 4. 预计算指标 =====
ema20=calc_ema(c4,EMA_P)
rsi14=calc_rsi(c4,RSI_P)
adx14=calc_adx(h4,l4,c4,14)

# MACD
ema12_c=calc_ema(c4,12); ema26_c=calc_ema(c4,26)
macd_line=[ema12_c[i]-ema26_c[i] for i in range(n)]
signal_line=[0.0]*n
for i in range(26,n):
    sl=sum(macd_line[max(0,i-9):i+1])/min(10,i-max(0,i-9)+1)
    signal_line[i]=sl if sl else 0.0001
macd_hist=[macd_line[i]-signal_line[i] for i in range(n)]

# ATR for SL sizing
atr_vals=[0.0]*n
for i in range(1,n):
    atr_vals[i]=max(h4[i]-l4[i], abs(h4[i]-c4[i-1]), abs(l4[i]-c4[i-1]))
atr14=[0.0]*n
for i in range(14,n):
    atr14[i]=sum(atr_vals[i-13:i+1])/14

# ===== 5. 模拟交易 =====
trades=[]
balance=CAPITAL
equity=CAPITAL
pos=None  # {'entry','side','sl','size','time'}
max_drawdown=0; peak=CAPITAL

warmup=50

for i in range(warmup,n-1):
    p=c4[i]
    if p<=0: continue
    
    # 持仓管理
    if pos:
        # 移动止损
        pnl=(p-pos['entry'])*pos['size']*pos['side']
        if pnl>=TRAIL_PROFIT:
            if pos['side']==1:
                ns=p-TRAIL_DIST
                if ns>pos['sl']: pos['sl']=ns
            else:
                ns=p+TRAIL_DIST
                if ns<pos['sl']: pos['sl']=ns
        
        # 止损检查
        hit_sl=(pos['side']==1 and l4[i]<=pos['sl']) or (pos['side']==-1 and h4[i]>=pos['sl'])
        if hit_sl:
            exit_p=pos['sl']
            pnl=(exit_p-pos['entry'])*pos['size']*pos['side']
            balance+=pnl
            trades.append({
                'entry_t':str(pos['time']),'exit_t':str(t4[i]),
                'entry':pos['entry'],'exit':exit_p,'pnl':pnl,
                'side':'LONG' if pos['side']==1 else 'SHORT','reason':'SL'
            })
            pos=None
            if balance>peak: peak=balance
            dd=(peak-balance)/peak*100
            if dd>max_drawdown: max_drawdown=dd
            continue
        
        # 信号反转平仓(RES反方向)
        e=ema20[i]; r=rsi14[i]
        curr_sig=1 if(p>e and RSI_LONG_LO<r<RSI_LONG_HI) else (-1 if(p<e and RSI_SHORT_LO<r<RSI_SHORT_HI) else 0)
        if pos['side']==1 and curr_sig==-1:
            exit_p=c4[i]
            pnl=(exit_p-pos['entry'])*pos['size']
            balance+=pnl
            trades.append({
                'entry_t':str(pos['time']),'exit_t':str(t4[i]),
                'entry':pos['entry'],'exit':exit_p,'pnl':pnl,
                'side':'LONG','reason':'反转'
            })
            pos=None
        elif pos['side']==-1 and curr_sig==1:
            exit_p=c4[i]
            pnl=(pos['entry']-exit_p)*pos['size']
            balance+=pnl
            trades.append({
                'entry_t':str(pos['time']),'exit_t':str(t4[i]),
                'entry':pos['entry'],'exit':exit_p,'pnl':pnl,
                'side':'SHORT','reason':'反转'
            })
            pos=None
        if balance>peak: peak=balance
        dd=(peak-balance)/peak*100
        if dd>max_drawdown: max_drawdown=dd
        continue
    
    # 无持仓: 信号检查
    e=ema20[i]; r=rsi14[i]; adx=adx14[i]; macd=macd_hist[i]
    sig=1 if(p>e and RSI_LONG_LO<r<RSI_LONG_HI) else (-1 if(p<e and RSI_SHORT_LO<r<RSI_SHORT_HI) else 0)
    
    if sig==0: continue
    
    # 确认过滤器
    # 1. ADX > 20 或 MACD同向
    adx_ok=adx>20 or (sig==1 and macd>0) or (sig==-1 and macd<0)
    if not adx_ok: continue
    
    # 2. 计算仓位
    sl_dist=max(SL_MIN, atr14[i]*SL_ATR_MULT)
    sl=p-sl_dist if sig==1 else p+sl_dist
    size=min(0.1, max(0.01, round(RISK_PER_TRADE/sl_dist, 2)))
    
    if size<0.01: continue
    
    # 开仓
    pos={
        'entry':p,'side':sig,'sl':sl,'size':size,'time':t4[i]
    }

# 最后未平仓
if pos:
    exit_p=c4[-1]
    pnl=(exit_p-pos['entry'])*pos['size']*pos['side']
    balance+=pnl
    trades.append({
        'entry_t':str(pos['time']),'exit_t':str(t4[-1]),
        'entry':pos['entry'],'exit':exit_p,'pnl':pnl,
        'side':'LONG' if pos['side']==1 else 'SHORT','reason':'结束'
    })

# ===== 6. 报告 =====
longs=[t for t in trades if t['side']=='LONG']
shorts=[t for t in trades if t['side']=='SHORT']
wins=[t for t in trades if t['pnl']>0]
losses=[t for t in trades if t['pnl']<=0]
total_pnl=sum(t['pnl'] for t in trades)

print(f'\n{"="*60}')
print(f'  回测结果')
print(f'{"="*60}')
print(f'本金: ${CAPITAL:,.0f} → 最终: ${balance:,.0f}')
print(f'收益: ${balance-CAPITAL:+,.0f} ({(balance/CAPITAL-1)*100:+.1f}%)')
print(f'交易: {len(trades)}笔 (多{len(longs)}/空{len(shorts)})')
print(f'胜率: {len(wins)/len(trades)*100:.1f}% ({len(wins)}赢/{len(losses)}输)' if trades else '胜率: N/A')
if wins: print(f'均赢: ${np.mean([t["pnl"] for t in wins]):,.0f}')
if losses: print(f'均亏: ${np.mean([t["pnl"] for t in losses]):,.0f}')
if wins and losses: print(f'盈亏比: {abs(np.mean([t["pnl"] for t in wins])/np.mean([t["pnl"] for t in losses])):.2f}')
print(f'最大回撤: {max_drawdown:.1f}%')
print(f'年化: {(balance/CAPITAL)**(1/((t4[-1]-t4[0]).days/365))-1:+.1%}')

print(f'\n按年:')
years={}
for t in trades:
    y=t['entry_t'][:4]
    years.setdefault(y,{'pnl':0,'count':0,'wins':0})
    years[y]['pnl']+=t['pnl']; years[y]['count']+=1
    if t['pnl']>0: years[y]['wins']+=1
for y in sorted(years):
    d=years[y]; wr=d['wins']/d['count']*100 if d['count'] else 0
    print(f'  {y}: {d["count"]}笔  净${d["pnl"]:+,.0f}  胜率{wr:.0f}%')

# 本月
now=datetime.now()
this_month=[t for t in trades if t['entry_t'].startswith(now.strftime('%Y-%m'))]
if this_month:
    mpnl=sum(t['pnl'] for t in this_month)
    print(f'  {now.strftime("%Y-%m")}: {len(this_month)}笔  净${mpnl:+,.0f}')

print(f'\n最近10笔:')
for t in trades[-10:]:
    print(f'  {t["entry_t"][:10]} {t["side"]:5s} ${t["entry"]:,.0f}→${t["exit"]:,.0f} {t["pnl"]:+,.0f} [{t["reason"]}]')

# Save
report={
    "start":str(t4[0]),"end":str(t4[-1]),
    "capital":CAPITAL,"final":round(balance,0),"pnl":round(balance-CAPITAL,0),
    "trades":len(trades),"win_rate":round(len(wins)/len(trades)*100,1) if trades else 0,
    "max_dd":round(max_drawdown,1),"sharpe":0,
}
with open("D:/BTC/backtest_2021_now.json","w") as f: json.dump(report,f,indent=2)
print(f'\n报告: D:/BTC/backtest_2021_now.json')
