#!/usr/bin/env python3
"""融合模型预测器 — 4周期MLP概率 → 高层融合 → 方向+置信度"""
import pickle, numpy as np, bisect, warnings
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta
import MetaTrader5 as mt5

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
SYMBOL = "BTCUSD"

# 模型路径
MODEL_DIR = "D:/BTC/nn_vote"
FUSION_DIR = "D:/BTC/nn_fusion_v2"

# 懒加载
_base_models = None
_base_scalers = None
_fusion_model = None
_model_names = ['1h', '4h', '1d', '30m']
_tf_map = {
    '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
    '1d': mt5.TIMEFRAME_D1, '30m': mt5.TIMEFRAME_M30,
}

def _load_models():
    global _base_models, _base_scalers, _fusion_model
    if _base_models is not None:
        return True
    try:
        _base_models = {}
        _base_scalers = {}
        for n in _model_names:
            with open(f"{MODEL_DIR}/model_{n}.pkl", "rb") as f:
                _base_models[n] = pickle.load(f)
            with open(f"{MODEL_DIR}/scaler_{n}.pkl", "rb") as f:
                _base_scalers[n] = pickle.load(f)
        with open(f"{FUSION_DIR}/fusion_MLP.pkl", "rb") as f:
            _fusion_model = pickle.load(f)
        return True
    except Exception as e:
        print(f"融合模型加载失败: {e}")
        return False

def _make_features(rates, lookback=20):
    """与训练时一致的特征提取"""
    cl = np.array([r[4] for r in rates], float)
    hi = np.array([r[2] for r in rates], float)
    lo = np.array([r[3] for r in rates], float)
    vol = np.array([r[5] for r in rates], float)
    n = len(cl)
    if n < lookback + 5:
        return None, None
    w = cl[-lookback:]; p = cl[-1]
    f = [
        (cl[-1]-cl[-2])/cl[-2]*100,
        (cl[-1]-cl[-7])/cl[-7]*100 if n >= 7 else 0,
        (cl[-1]-cl[-lookback])/cl[-lookback]*100 if n > lookback else 0,
        np.std(np.diff(w)/w[:-1])*100,
        (hi[-1]-lo[-1])/p*100,
    ]
    delta = np.diff(cl[-15:])
    g = np.mean(delta[delta>0]) if np.any(delta>0) else 0
    l = -np.mean(delta[delta<0]) if np.any(delta<0) else 0.0001
    f.append(100-100/(1+g/l))
    f.append((p-np.mean(w))/np.std(w)*10 if np.std(w)>0 else 0)
    f.append(np.log1p(vol[-1])-np.log1p(np.mean(vol[-lookback:])))
    return np.array([f]), datetime.fromtimestamp(rates[-1][0])

def predict(symbol=SYMBOL, mt5_path=MT5_PATH):
    """
    融合预测: 返回 {"direction": "LONG"/"SHORT"/"HOLD", "confidence": float, "ready": bool}
    严格因果: 只用决策时刻之前的数据
    """
    if not _load_models():
        return {"ready": False, "error": "模型未加载"}

    try:
        mt5.initialize(path=mt5_path)
        mt5.symbol_select(symbol, True)

        probas = {}
        now = datetime.now()

        for name in _model_names:
            tf = _tf_map[name]
            lookback = 24
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, lookback + 20)
            if rates is None or len(rates) < lookback + 5:
                probas[name] = 0.5  # 缺失填中性
                continue

            feat, t = _make_features(rates, lookback)
            if feat is None:
                probas[name] = 0.5
                continue

            X_s = _base_scalers[name].transform(feat)
            prob = float(_base_models[name].predict_proba(X_s)[0][1])
            probas[name] = prob

        mt5.shutdown()

        # 融合预测
        vec = np.array([[probas.get(n, 0.5) for n in _model_names]])
        pred = int(_fusion_model.predict(vec)[0])
        proba = float(_fusion_model.predict_proba(vec)[0][1])

        direction = "LONG" if pred == 1 else "SHORT"
        return {
            "ready": True,
            "direction": direction,
            "confidence": round(proba, 3),
            "raw_probas": {n: round(probas[n], 3) for n in _model_names},
            "time": now.strftime("%H:%M:%S"),
        }

    except Exception as e:
        try: mt5.shutdown()
        except: pass
        return {"ready": False, "error": str(e)}
