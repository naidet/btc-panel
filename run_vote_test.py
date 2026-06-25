"""多周期MLP投票系统 — 4h对齐 多数决"""
import numpy as np, pickle, json, warnings
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
import MetaTrader5 as mt5, os

OUT = "D:/BTC/nn_vote"
os.makedirs(OUT, exist_ok=True)

mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe')
mt5.symbol_select('BTCUSD', True)

# ===== 1. 数据扫描 =====
tfs = {
    '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4, '1d': mt5.TIMEFRAME_D1,
    '30m': mt5.TIMEFRAME_M30, '15m': mt5.TIMEFRAME_M15,
}

all_data = {}
for name, tf in tfs.items():
    rates = mt5.copy_rates_range('BTCUSD', tf, datetime(2023,1,1), datetime.now())
    if rates is not None and len(rates) > 100:
        t0 = datetime.fromtimestamp(rates[0][0]); t1 = datetime.fromtimestamp(rates[-1][0])
        r2025 = [r for r in rates if datetime.fromtimestamp(r[0]) >= datetime(2025,1,1)]
        print(f'{name:>4s}: 总数{len(rates)}  2025年{len(r2025)}根  {t0.date()}~{t1.date()}')
        if len(r2025) >= 30:
            all_data[name] = rates
    else:
        print(f'{name:>4s}: 无数据')

mt5.shutdown()

# ===== 2. 特征 + 模型训练 =====
def make_features(rates, lookback=20):
    cl = np.array([r[4] for r in rates], float)
    hi = np.array([r[2] for r in rates], float)
    lo = np.array([r[3] for r in rates], float)
    vol = np.array([r[5] for r in rates], float)
    n = len(cl)
    X, times = [], []
    for i in range(lookback+5, n):
        w = cl[i-lookback:i]; p = cl[i]
        f = [
            (cl[i]-cl[i-1])/cl[i-1]*100,
            (cl[i]-cl[i-6])/cl[i-6]*100 if i>=6 else 0,
            (cl[i]-cl[i-lookback])/cl[i-lookback]*100,
            np.std(np.diff(w)/w[:-1])*100,
            (hi[i]-lo[i])/p*100,
        ]
        delta = np.diff(cl[i-14:i+1])
        g = np.mean(delta[delta>0]) if np.any(delta>0) else 0
        l = -np.mean(delta[delta<0]) if np.any(delta<0) else 0.0001
        f.append(100-100/(1+g/l))
        f.append((p-np.mean(w))/np.std(w)*10 if np.std(w)>0 else 0)
        f.append(np.log1p(vol[i])-np.log1p(np.mean(vol[i-lookback:i])))
        X.append(f); times.append(datetime.fromtimestamp(rates[i][0]))
    return np.array(X), np.array(times)

models, scalers, test_data = {}, {}, {}

for name, rates in all_data.items():
    print(f'\n--- {name} ---')
    X_all, T_all = make_features(rates)
    Y_all = np.array([1 if rates[i+1][4] > rates[i][4] else 0 for i in range(25, len(rates)-1)])
    L = min(len(X_all), len(Y_all))
    X_all, Y_all, T_all = X_all[:L], Y_all[:L], T_all[:L]
    
    mask_train = np.array([t < datetime(2025,1,1) for t in T_all])
    mask_test = np.array([t >= datetime(2025,1,1) for t in T_all])
    
    X_tr = X_all[mask_train]; Y_tr = Y_all[mask_train]
    if len(X_tr) < 50: print(f'  训练集太小({len(X_tr)}), 跳过'); continue
    
    sc = StandardScaler(); X_tr_s = sc.fit_transform(X_tr)
    m = MLPClassifier((16,8), max_iter=1500, random_state=42, early_stopping=True)
    m.fit(X_tr_s, Y_tr)
    print(f'  训练: {len(Y_tr)}样本  精度={m.score(X_tr_s, Y_tr)*100:.1f}%')
    
    if mask_test.sum() > 10:
        X_te = X_all[mask_test]; Y_te = Y_all[mask_test]; T_te = T_all[mask_test]
        X_te_s = sc.transform(X_te)
        pred_te = m.predict(X_te_s)
        print(f'  测试: {len(Y_te)}样本  精度={m.score(X_te_s, Y_te)*100:.1f}%')
        test_data[name] = {'pred': pred_te, 'times': T_te}
    
    models[name] = m; scalers[name] = sc

# ===== 3. 对齐到4h并投票 =====
def align_to_4h(pred, times):
    aligned = {}
    for p, t in zip(pred, times):
        slot_h = (t.hour // 4) * 4
        key = t.replace(hour=slot_h, minute=0, second=0, microsecond=0)
        if key not in aligned or t > aligned[key][1]:
            aligned[key] = (p, t)
    return {k: v[0] for k, v in aligned.items()}

print(f'\n{"="*55}')
print(f'  投票回测 (4h对齐, 2025年)')
print(f'{"="*55}')

votes_by_time = {}
for name, td in test_data.items():
    aligned = align_to_4h(td['pred'], td['times'])
    for t, v in aligned.items():
        votes_by_time.setdefault(t, []).append(v)

sorted_times = sorted(votes_by_time.keys())
valid = {t: v for t, v in votes_by_time.items() if len(v) >= 2}
print(f'投票时刻: {len(valid)}个 (>=2模型参与, 共{len(sorted_times)}个时间点)')

# ===== 4. 价格 =====
mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe')
mt5.symbol_select('BTCUSD', True)
r1h = mt5.copy_rates_range('BTCUSD', mt5.TIMEFRAME_H1, datetime(2025,1,1), datetime.now())
mt5.shutdown()
ph = {}
for r in r1h: ph[datetime.fromtimestamp(r[0])] = r[4]

# ===== 5. 交易 =====
trades = []; signal = 0; entry = 0
for i, t in enumerate(sorted_times):
    if t not in valid: continue
    votes = valid[t]
    buys = sum(1 for v in votes if v == 1)
    total_v = len(votes)
    br = buys/total_v; sr = 1 - br
    
    p = None
    for h in range(0, 4):
        tt = t + timedelta(hours=h)
        if tt in ph: p = ph[tt]; break
    if p is None: continue
    
    if signal == 0:
        if br >= 0.6: signal = 1; entry = p; et = t
        elif sr >= 0.6: signal = -1; entry = p; et = t
    else:
        close = False
        if (signal == 1 and sr >= 0.6) or (signal == -1 and br >= 0.6):
            close = True
        if close or i == len(sorted_times)-1:
            pnl = (p - entry) * signal
            trades.append({'entry':entry,'exit':p,'pnl':pnl,'votes':total_v,'ratio':f'{br*100:.0f}/{sr*100:.0f}'})
            signal = 0

# ===== 6. 报告 =====
wins = [t for t in trades if t['pnl']>0]
losses = [t for t in trades if t['pnl']<=0]
total_pnl = sum(t['pnl'] for t in trades)

print(f'\n{"="*55}')
print(f'  结果')
print(f'{"="*55}')
print(f'模型: {list(models.keys())}')
print(f'交易: {len(trades)}笔 | 胜: {len(wins)} | 负: {len(losses)}')
print(f'胜率: {len(wins)/len(trades)*100:.1f}%' if trades else '胜率: N/A')
print(f'净利: ${total_pnl:,.0f}')
if wins: print(f'均赢: ${np.mean([t["pnl"] for t in wins]):,.0f}')
if losses: print(f'均亏: ${np.mean([t["pnl"] for t in losses]):,.0f}')
if wins and losses: print(f'盈亏比: {abs(np.mean([t["pnl"] for t in wins])/np.mean([t["pnl"] for t in losses])):.2f}')

print(f'\n最近5笔:')
for t in trades[-5:]:
    print(f'  ${t["entry"]:,.0f}→${t["exit"]:,.0f} {t["pnl"]:+,.0f} [{t["votes"]}票 {t["ratio"]}]')

# Save
for name, m in models.items():
    with open(f"{OUT}/model_{name}.pkl","wb") as f: pickle.dump(m, f)
    with open(f"{OUT}/scaler_{name}.pkl","wb") as f: pickle.dump(scalers[name], f)

rpt = {"trades":len(trades),"wins":len(wins),"losses":len(losses),
       "win_rate":round(len(wins)/len(trades)*100,1) if trades else 0,
       "total_pnl":round(total_pnl,0),"models":list(models.keys())}
with open(f"{OUT}/report.json","w") as f: json.dump(rpt,f,indent=2)
print(f'\nSaved: {OUT}/')
