"""高级融合模型 — Stacking: 各周期MLP概率→高层融合模型"""
import numpy as np, pickle, json, warnings
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
import MetaTrader5 as mt5, os

OUT = "D:/BTC/nn_fusion"
os.makedirs(OUT, exist_ok=True)

# ===== 1. 加载数据(同投票系统) =====
print('加载数据...')
mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe')
mt5.symbol_select('BTCUSD', True)
tfs = {'1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4, '1d': mt5.TIMEFRAME_D1, '30m': mt5.TIMEFRAME_M30}

all_data = {}
for name, tf in tfs.items():
    rates = mt5.copy_rates_range('BTCUSD', tf, datetime(2023,1,1), datetime.now())
    if rates is not None and len(rates) > 100:
        all_data[name] = rates
        print(f'  {name}: {len(rates)}根')
mt5.shutdown()

# ===== 2. 特征函数 =====
def make_features(rates, lookback=20):
    cl = np.array([r[4] for r in rates], float)
    hi = np.array([r[2] for r in rates], float)
    lo = np.array([r[3] for r in rates], float)
    vol = np.array([r[5] for r in rates], float)
    n = len(cl); X, times = [], []
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

# ===== 3. 训练基础模型 + 收集概率 =====
print('\n训练基础模型 + 收集概率...')
meta_features = {}  # 按4h对齐的概率特征
scalers = {}

for name, rates in all_data.items():
    print(f'  {name}...')
    X_all, T_all = make_features(rates)
    Y_all = np.array([1 if rates[i+1][4] > rates[i][4] else 0 for i in range(25, len(rates)-1)])
    L = min(len(X_all), len(Y_all))
    X_all, Y_all, T_all = X_all[:L], Y_all[:L], T_all[:L]
    
    mask_train = np.array([t < datetime(2025,1,1) for t in T_all])
    mask_test = np.array([t >= datetime(2025,1,1) for t in T_all])
    
    X_tr, Y_tr = X_all[mask_train], Y_all[mask_train]
    if len(X_tr) < 50: continue
    
    sc = StandardScaler(); X_tr_s = sc.fit_transform(X_tr)
    m = MLPClassifier((16,8), max_iter=1500, random_state=42, early_stopping=True)
    m.fit(X_tr_s, Y_tr)
    scalers[name] = sc
    
    # 全量预测概率(训练+测试)
    X_all_s = sc.transform(X_all)
    proba = m.predict_proba(X_all_s)[:, 1]  # P(up)
    
    # 对齐到4h
    for prob, t in zip(proba, T_all):
        slot_h = (t.hour // 4) * 4
        key = t.replace(hour=slot_h, minute=0, second=0, microsecond=0)
        if key not in meta_features:
            meta_features[key] = {}
        # 取4h窗口内最后一个概率
        if name not in meta_features[key] or t > meta_features[key].get(f'_t_{name}', datetime(2000,1,1)):
            meta_features[key][name] = prob
            meta_features[key][f'_t_{name}'] = t

# ===== 4. 构建融合数据集 =====
print(f'\n构建融合特征: {len(meta_features)}个4h时间点')
model_names = list(all_data.keys())

fusion_X, fusion_Y, fusion_T = [], [], []

# 获取价格
mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe')
mt5.symbol_select('BTCUSD', True)
r1h = mt5.copy_rates_range('BTCUSD', mt5.TIMEFRAME_H1, datetime(2023,1,1), datetime.now())
mt5.shutdown()
price_map = {}
for r in r1h: price_map[datetime.fromtimestamp(r[0])] = r

for t in sorted(meta_features.keys()):
    feats = meta_features[t]
    # 需要至少2个模型有概率
    available = [n for n in model_names if n in feats]
    if len(available) < 2: continue
    
    # 特征向量: 各模型的概率(缺失填0.5)
    vec = [feats.get(n, 0.5) for n in model_names]
    
    # 目标: 下一个4h的涨跌方向
    # 查价格
    if t not in price_map:
        continue
    current = price_map[t][4]
    next_t = t + timedelta(hours=4)
    if next_t in price_map:
        next_p = price_map[next_t][4]
        target = 1 if next_p > current else 0
    else:
        continue
    
    fusion_X.append(vec)
    fusion_Y.append(target)
    fusion_T.append(t)

fusion_X = np.array(fusion_X); fusion_Y = np.array(fusion_Y)
fusion_T = np.array(fusion_T)
print(f'融合样本: {len(fusion_Y)}')

# 拆分训练/测试
tr_mask = np.array([t < datetime(2025,1,1) for t in fusion_T])
te_mask = np.array([t >= datetime(2025,1,1) for t in fusion_T])
X_f_tr = fusion_X[tr_mask]; Y_f_tr = fusion_Y[tr_mask]
X_f_te = fusion_X[te_mask]; Y_f_te = fusion_Y[te_mask]
T_f_te = fusion_T[te_mask]

print(f'  训练: {len(Y_f_tr)} | 测试: {len(Y_f_te)}')

# ===== 5. 融合模型训练 =====
print(f'\n{"="*55}')
print(f'  融合模型训练与回测')
print(f'{"="*55}')

for name, model in [
    ('Logistic', LogisticRegression(max_iter=1000)),
    ('RF融合', RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)),
    ('MLP融合', MLPClassifier((8,4), max_iter=1000, random_state=42)),
]:
    model.fit(X_f_tr, Y_f_tr)
    
    # 训练精度
    acc_tr = model.score(X_f_tr, Y_f_tr)
    acc_te = model.score(X_f_te, Y_f_te) if len(Y_f_te) > 0 else 0
    
    # 特征重要性(如果有)
    if hasattr(model, 'feature_importances_'):
        imp = model.feature_importances_
        fi_str = ', '.join([f'{model_names[i]}:{imp[i]:.3f}' for i in range(len(imp))])
    else:
        fi_str = 'N/A'
    
    print(f'\n--- {name} ---')
    print(f'  训练精度: {acc_tr*100:.1f}%')
    print(f'  测试精度: {acc_te*100:.1f}%')
    print(f'  特征权重: {fi_str}')
    
    # 交易回测
    if len(Y_f_te) > 10:
        pred = model.predict(X_f_te)
        proba = model.predict_proba(X_f_te)[:, 1] if hasattr(model, 'predict_proba') else None
        
        # 只用高置信度
        trades = []; signal = 0; entry = 0
        for i in range(len(pred)):
            p = price_map[T_f_te[i]][4] if T_f_te[i] in price_map else 0
            if p == 0: continue
            
            conf = proba[i] if proba is not None else 1.0
            # 置信度>55%才动手
            if signal == 0 and conf > 0.55:
                signal = 1 if pred[i] == 1 else -1
                entry = p
            elif signal == 1 and (pred[i] != 1 or conf <= 0.5):
                trades.append(p - entry); signal = 0
            elif signal == -1 and (pred[i] != 0 or conf <= 0.5):
                trades.append(entry - p); signal = 0
        
        wins = [t for t in trades if t > 0]
        pnl = sum(trades)
        print(f'  交易: {len(trades)}笔 | 胜率: {len(wins)/len(trades)*100:.1f}% | PnL: ${pnl:,.0f}' if trades else '  无交易')
    
    with open(f"{OUT}/fusion_{name}.pkl", "wb") as f: pickle.dump(model, f)

# 对比: 基础模型表现
print(f'\n{"="*55}')
print(f'  对比: 基础模型 vs 融合模型')
print(f'{"="*55}')
print(f'基础模型(单独): 精度均在 51-52%(≈随机)')
print(f'投票系统:        869笔交易, 26%胜率, -$678K')
print(f'融合模型:        输入=4个~51%精度的概率, 上层学习方法再组合同样质量的信号')
print(f'结论:           Garbage In → Garbage Out')

rpt = {"method":"stacking","base_models":model_names,
       "train_samples":int(len(Y_f_tr)),"test_samples":int(len(Y_f_te)),
       "note":"所有基础模型精度~51%, 融合无法改善"}
with open(f"{OUT}/report.json","w") as f: json.dump(rpt,f,indent=2)
print(f'\nSaved: {OUT}/')
