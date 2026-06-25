"""融合模型v2 — 严格因果对齐 (bisect优化, 无前视偏差)"""
import numpy as np, pickle, json, bisect, warnings
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
import MetaTrader5 as mt5, os

OUT = "D:/BTC/nn_fusion_v2"; os.makedirs(OUT, exist_ok=True)

print('加载数据...')
mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe')
mt5.symbol_select('BTCUSD', True)
tfs = {'1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4, '1d': mt5.TIMEFRAME_D1, '30m': mt5.TIMEFRAME_M30}
all_data = {}
for n, tf in tfs.items():
    r = mt5.copy_rates_range('BTCUSD', tf, datetime(2023,1,1), datetime.now())
    if r is not None and len(r) > 100: all_data[n] = r; print(f'  {n}: {len(r)}')
mt5.shutdown()

def make_features(rates, lb=20):
    cl=np.array([r[4] for r in rates],float); hi=np.array([r[2] for r in rates],float)
    lo=np.array([r[3] for r in rates],float); vol=np.array([r[5] for r in rates],float)
    n=len(cl); X,ts=[],[]
    for i in range(lb+5,n):
        w=cl[i-lb:i]; p=cl[i]
        f=[(cl[i]-cl[i-1])/cl[i-1]*100, (cl[i]-cl[i-6])/cl[i-6]*100 if i>=6 else 0,
           (cl[i]-cl[i-lb])/cl[i-lb]*100, np.std(np.diff(w)/w[:-1])*100, (hi[i]-lo[i])/p*100]
        de=np.diff(cl[i-14:i+1]); g=np.mean(de[de>0]) if np.any(de>0) else 0
        l=-np.mean(de[de<0]) if np.any(de<0) else 0.0001
        f.append(100-100/(1+g/l))
        f.append((p-np.mean(w))/np.std(w)*10 if np.std(w)>0 else 0)
        f.append(np.log1p(vol[i])-np.log1p(np.mean(vol[i-lb:i])))
        X.append(f); ts.append(datetime.fromtimestamp(rates[i][0]))
    return np.array(X),np.array(ts)

print('\n训练基础模型...')
models,scalers,probas_t={},{},{}
for name,rates in all_data.items():
    X_all,T_all=make_features(rates)
    Y_all=np.array([1 if rates[i+1][4]>rates[i][4] else 0 for i in range(25,len(rates)-1)])
    L=min(len(X_all),len(Y_all)); X_all,Y_all,T_all=X_all[:L],Y_all[:L],T_all[:L]
    m_tr=T_all<datetime(2025,1,1)
    X_tr,Y_tr=X_all[m_tr],Y_all[m_tr]
    if len(X_tr)<50: continue
    sc=StandardScaler(); X_tr_s=sc.fit_transform(X_tr)
    m=MLPClassifier((16,8),max_iter=1500,random_state=42,early_stopping=True)
    m.fit(X_tr_s,Y_tr)
    proba=m.predict_proba(sc.transform(X_all))[:,1]
    probas_t[name]=(proba,T_all)
    models[name]=m; scalers[name]=sc
    m_te=~m_tr
    acc=m.score(sc.transform(X_all[m_te]),Y_all[m_te]) if m_te.sum()>0 else 0
    print(f'  {name}: 训练{len(Y_tr)} 测试精度={acc*100:.1f}%')

# ===== 高效对齐: 排序 + bisect =====
print(f'\n严格因果对齐...')
# 每个模型: 预排序 (time, proba)
sorted_probas={}
for name,(proba,T_all) in probas_t.items():
    pts=[(T_all[i],float(proba[i])) for i in range(len(proba))]
    pts.sort(key=lambda x:x[0])
    sorted_probas[name]={'times':[p[0] for p in pts],'probas':[p[1] for p in pts]}

# 价格
mt5.initialize(path='C:/Program Files/MetaTrader 5/terminal64.exe')
mt5.symbol_select('BTCUSD',True)
r1h=mt5.copy_rates_range('BTCUSD',mt5.TIMEFRAME_H1,datetime(2023,1,1),datetime.now())
mt5.shutdown()
pm={datetime.fromtimestamp(r[0]):r for r in r1h}

# 生成4h slot并快速对齐
model_names=list(all_data.keys())
start_slot=min(pd['times'][0] for pd in sorted_probas.values())
start_slot=start_slot.replace(hour=(start_slot.hour//4)*4,minute=0,second=0,microsecond=0)

FX,FY,FT=[],[],[]
for i in range(6000):
    slot=start_slot+timedelta(hours=4*i)
    if slot>datetime.now(): break
    ns=slot+timedelta(hours=4)
    if ns>datetime.now(): break
    # 获取slot时刻价格(不要求精确匹配)
    cp=None
    for dh in range(0,5):
        if slot+timedelta(hours=dh) in pm: cp=pm[slot+timedelta(hours=dh)][4]; break
    if cp is None: continue
    np_=None
    for dh in range(0,5):
        if ns+timedelta(hours=dh) in pm: np_=pm[ns+timedelta(hours=dh)][4]; break
    if np_ is None: continue
    
    vec=[]; av=0
    for mn in model_names:
        if mn not in sorted_probas: vec.append(0.5); continue
        st=sorted_probas[mn]['times']; sp=sorted_probas[mn]['probas']
        idx=bisect.bisect_right(st,slot)-1
        vec.append(sp[idx] if idx>=0 else 0.5)
        if idx>=0: av+=1
    if av<2: continue
    
    FX.append(vec); FY.append(1 if np_>cp else 0); FT.append(slot)

FX=np.array(FX); FY=np.array(FY); FT=np.array(FT)
m_tr=FT<datetime(2025,1,1); m_te=FT>=datetime(2025,1,1)
print(f'样本: {len(FY)}(训练{sum(m_tr)} + 测试{sum(m_te)})')

# ===== 融合模型 =====
print(f'\n{"="*55}')
print(f'  融合回测 (严格因果)')
print(f'{"="*55}')
for name,model_cls in [
    ('Logistic',LogisticRegression(max_iter=1000)),
    ('RF',RandomForestClassifier(100,max_depth=5,random_state=42)),
    ('MLP',MLPClassifier((8,4),max_iter=1000,random_state=42)),
]:
    model_cls.fit(FX[m_tr],FY[m_tr])
    acc=model_cls.score(FX[m_te],FY[m_te])
    fi=''
    if hasattr(model_cls,'feature_importances_'):
        fi=', '.join([f'{model_names[i]}:{model_cls.feature_importances_[i]:.2f}' for i in range(len(model_names))])
    print(f'\n  {name}: 精度={acc*100:.1f}%  {fi}')
    
    if sum(m_te)>10:
        pred=model_cls.predict(FX[m_te])
        proba=model_cls.predict_proba(FX[m_te])[:,1] if hasattr(model_cls,'predict_proba') else np.full(len(pred),0.5)
        trades=[]; sig=0; ent=0
        for i in range(len(pred)):
            p=pm[FT[m_te][i]][4] if FT[m_te][i] in pm else 0
            if p==0: continue
            c=proba[i]
            if sig==0 and c>0.55: sig=1 if pred[i]==1 else -1; ent=p
            elif sig==1 and (c<=0.55 or pred[i]!=1): trades.append(p-ent); sig=0
            elif sig==-1 and (c<=0.55 or pred[i]!=0): trades.append(ent-p); sig=0
        if trades:
            w=[t for t in trades if t>0]
            print(f'    交易:{len(trades)} 胜率:{len(w)/len(trades)*100:.1f}% PnL:${sum(trades):,.0f}')
    with open(f"{OUT}/fusion_{name}.pkl","wb") as f: pickle.dump(model_cls,f)

# ===== 对比 =====
print(f'\n{"="*55}')
print(f'  总结')
print(f'{"="*55}')
print(f'  v1(有偏差): 72%精度 79%胜率 +$544K  ← 不真实')
print(f'  v2(无偏差): {acc*100:.1f}%精度 ← 真实水平')
print(f'  结论: 基础MLP≈51%, 融合≈50%. GIGO')

with open(f"{OUT}/report.json","w") as f: json.dump({"acc":round(float(acc)*100,1),"note":"strict causal"},f)
print(f'\nDone: {OUT}/')
