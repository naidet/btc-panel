#!/usr/bin/env python3
"""
HMM 市场状态识别 — Phase 3
===========================
参考: MQL5 隐马尔可夫模型文章 (https://www.mql5.com/zh/articles/17917)

流程:
  1. MT5 获取 XAUUSD H4 K线
  2. 多周期波动率 + 动量 + 布林带宽度 → 特征矩阵
  3. K-means 预聚类 → 初始化 HMM 先验
  4. GaussianHMM 训练 → 3~5 个隐藏状态
  5. 分析各状态收益特征 → 映射: 趋势/震荡/过渡
"""

import os, sys, time, datetime, warnings
import numpy as np
from collections import defaultdict

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 引用现有模块 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_trader import Bar, calc_ema, calc_rsi, calc_atr

# ═══════════════════════════════════════════
# 1. 获取数据
# ═══════════════════════════════════════════

def fetch_mt5_h4(symbol: str = "XAUUSD", start_year: int = 2021):
    """从 MT5 获取 H4 K线"""
    import MetaTrader5 as mt5
    mp = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    if not mt5.initialize(path=mp):
        print("  ❌ MT5 初始化失败"); return []

    # 尝试多个起始年份
    for sy in [start_year, 2023, 2024]:
        rates = mt5.copy_rates_range(
            symbol, mt5.TIMEFRAME_H4,
            datetime.datetime(sy, 1, 1), datetime.datetime.now()
        )
        if rates is not None and len(rates) > 50:
            break
        print(f"  ⚠️ {symbol} H4 {sy}~无数据")

    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print(f"  ❌ {symbol} H4 完全无数据"); return []

    bars = []
    for r in rates:
        bars.append(Bar(
            time=datetime.datetime.fromtimestamp(r[0], tz=datetime.timezone.utc),
            open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]
        ))
    bars.sort(key=lambda b: b.time)
    return bars


# ═══════════════════════════════════════════
# 2. 特征提取 (仿 MQL5 文章)
# ═══════════════════════════════════════════

def compute_features(bars: list) -> np.ndarray:
    """
    特征:
      - period_meta[0]: 5周期标准差 (波动率主特征)
      - periods[0..9]: 5/35/65/95/125/155/185/215/245/275 标准差
      - ROC(5): 5周期价格变化率
      - BB_width: 布林带宽度 (上轨-下轨)/中轨
    """
    n = len(bars)
    closes = np.array([b.close for b in bars])
    highs = np.array([b.high for b in bars])
    lows = np.array([b.low for b in bars])

    # 周期窗口: 5, 35, 65, 95, 125, 155, 185, 215, 245, 275
    periods = list(range(5, 300, 30))  # [5, 35, 65, 95, 125, 155, 185, 215, 245, 275]
    n_features = len(periods) + 2  # +ROC +BB_width
    features = np.full((n, n_features), np.nan)

    # 20周期 SMA (用于布林带)
    sma20 = np.full(n, np.nan)
    for i in range(19, n):
        sma20[i] = np.mean(closes[i-19:i+1])

    for i in range(n):
        feat = []
        for p in periods:
            if i >= p - 1:
                feat.append(np.std(closes[i-p+1:i+1]))
            else:
                feat.append(np.nan)

        # ROC(5)
        if i >= 5:
            feat.append((closes[i] - closes[i-5]) / closes[i-5] * 100)
        else:
            feat.append(np.nan)

        # BB 宽度
        if i >= 19 and not np.isnan(sma20[i]):
            std20 = np.std(closes[i-19:i+1])
            feat.append((2 * std20) / sma20[i] * 100)
        else:
            feat.append(np.nan)

        features[i] = feat

    return features


# ═══════════════════════════════════════════
# 3. 训练 HMM
# ═══════════════════════════════════════════

def train_hmm(features: np.ndarray, n_states: int = 5, random_state: int = 42):
    """
    K-means 预聚类 → GaussianHMM
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from hmmlearn import hmm

    # 只取完整行
    mask = ~np.isnan(features).any(axis=1)
    X = features[mask]
    print(f"  完整样本: {len(X):,} / {len(features):,}")

    # 标准化
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # K-means 预聚类
    print(f"  K-means (n={n_states})...")
    km = KMeans(n_clusters=n_states, random_state=random_state, n_init=10)
    labels = km.fit_predict(X_scaled)

    # 计算先验
    initial_probs = np.bincount(labels, minlength=n_states) / len(labels)

    # 转移矩阵
    trans_mat = np.zeros((n_states, n_states))
    for i in range(len(labels) - 1):
        trans_mat[labels[i], labels[i+1]] += 1
    for i in range(n_states):
        row_sum = trans_mat[i].sum()
        if row_sum > 0:
            trans_mat[i] /= row_sum
        else:
            trans_mat[i] = 1.0 / n_states

    # 注入先验
    means_prior = km.cluster_centers_
    covars_prior = np.zeros((n_states, X_scaled.shape[1]))
    for i in range(n_states):
        mask_i = labels == i
        if mask_i.sum() > 1:
            covars_prior[i] = np.var(X_scaled[mask_i], axis=0)
        else:
            covars_prior[i] = 1.0

    # GaussianHMM
    print(f"  GaussianHMM training (n_iter=100)...")
    model = hmm.GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=100,
        random_state=random_state,
        init_params="",  # 使用自定义先验
    )
    model.startprob_ = initial_probs
    model.transmat_ = trans_mat
    model.means_ = means_prior
    model.covars_ = covars_prior

    model.fit(X_scaled)
    state_seq = model.predict(X_scaled)

    return model, scaler, state_seq, X_scaled, mask


# ═══════════════════════════════════════════
# 4. 分析各状态
# ═══════════════════════════════════════════

def analyze_states(state_seq: np.ndarray, bars: list, mask: np.ndarray):
    """计算每个状态的统计特征"""
    closes = np.array([b.close for b in bars])[mask]
    times = np.array([b.time for b in bars])[mask]

    n_states = int(state_seq.max()) + 1
    stats = {}

    for s in range(n_states):
        idx = state_seq == s
        count = idx.sum()
        if count == 0:
            continue

        # 价格变化
        s_prices = closes[idx]
        mean_return = (s_prices[-1] / s_prices[0] - 1) * 100 if len(s_prices) > 1 else 0

        # 未来N根K线收益 (状态切换后)
        future_returns = []
        for i in range(len(state_seq)):
            if state_seq[i] == s:
                look_ahead = min(i + 1, len(state_seq) - 1)
                if look_ahead > i:
                    future_returns.append(
                        (closes[look_ahead] / closes[i] - 1) * 100
                    )

        avg_future = np.mean(future_returns) if future_returns else 0

        stats[int(s)] = {
            "count": int(count),
            "pct": count / len(state_seq) * 100,
            "mean_return": mean_return,
            "avg_future_pct": avg_future,
            "volatility": float(np.std(np.diff(s_prices) / s_prices[:-1]) * 10000),
        }

    return stats


def map_states(stats: dict) -> dict:
    """根据特征自动映射状态 → 市场体制"""
    # 按 avg_future_pct 排序, 涨幅最大的=看涨, 跌幅最大=看跌
    sorted_states = sorted(stats.items(), key=lambda x: x[1]["avg_future_pct"], reverse=True)

    mapping = {}
    for rank, (state_id, info) in enumerate(sorted_states):
        if rank == 0 and info["avg_future_pct"] > 0.01:
            mapping[state_id] = "📈 强趋势上涨"
        elif rank == len(sorted_states) - 1 and info["avg_future_pct"] < -0.01:
            mapping[state_id] = "📉 强趋势下跌"
        elif info["volatility"] < 0.5:
            mapping[state_id] = "📊 震荡整理"
        else:
            mapping[state_id] = "🔄 过渡/转折"

    return mapping


# ═══════════════════════════════════════════
# 5. 可视化
# ═══════════════════════════════════════════

def plot_result(bars, mask, state_seq, stats, mapping, save_path="hmm_states.png"):
    """生成状态划分图"""
    closes = np.array([b.close for b in bars])[mask]
    times = np.array([b.time for b in bars])[mask]
    n_states = int(state_seq.max()) + 1

    colors = ["#2196F3", "#F44336", "#FF9800", "#4CAF50", "#9C27B0"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={"height_ratios": [3, 1]})

    # 上: 价格 + 状态着色
    ax1.plot(times, closes, "#999", lw=0.5, alpha=0.7)
    for s in range(n_states):
        idx = state_seq == s
        if idx.sum() == 0:
            continue
        ax1.scatter(times[idx], closes[idx], c=colors[s % len(colors)],
                    s=2, alpha=0.4, label=f"状态{s}: {mapping.get(s,'?')}")

    ax1.set_ylabel("XAUUSD 价格")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)

    # 下: 状态分布
    state_pcts = [stats[s]["pct"] for s in sorted(stats.keys())]
    state_labels = [f"S{s}: {mapping.get(s,'?')}\n{stats[s]['pct']:.0f}%" 
                    for s in sorted(stats.keys())]
    ax2.barh(range(len(state_pcts)), state_pcts,
             color=[colors[s % len(colors)] for s in sorted(stats.keys())])
    ax2.set_yticks(range(len(state_pcts)))
    ax2.set_yticklabels(state_labels, fontsize=9)
    ax2.set_xlabel("占比 (%)")
    ax2.invert_yaxis()

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  📊 图表: {save_path}")


# ═══════════════════════════════════════════
# 6. 主程序
# ═══════════════════════════════════════════

def main(symbol="XAUUSD", n_states=5):
    print("=" * 60)
    print(f"  HMM 市场状态识别 — {symbol} H4")
    print(f"  GaussianHMM + K-means 先验 | n_states={n_states}")
    print("=" * 60)

    # 1. 数据
    print("\n[1/5] 获取数据 (MT5)...")
    bars = fetch_mt5_h4(symbol)
    if not bars:
        print("  ❌ 无法获取数据"); return
    print(f"  {bars[0].time.strftime('%Y-%m-%d')} ~ {bars[-1].time.strftime('%Y-%m-%d')}")
    print(f"  {len(bars):,} 根 H4 K线")
    print(f"  ${bars[0].close:.2f} → ${bars[-1].close:.2f}")

    # 2. 特征
    print("\n[2/5] 提取特征...")
    t0 = time.time()
    features = compute_features(bars)
    print(f"  特征维度: {features.shape[1]} (耗时 {time.time()-t0:.1f}s)")

    # 3. 训练
    print("\n[3/5] 训练 HMM...")
    model, scaler, state_seq, X_scaled, mask = train_hmm(features, n_states)
    print(f"  收敛: {model.monitor_.converged}")

    # 转移矩阵
    print("\n  转移矩阵:")
    print("    " + " ".join(f"S{i:>5}" for i in range(n_states)))
    for i in range(n_states):
        row = " ".join(f"{model.transmat_[i][j]:5.1%}" for j in range(n_states))
        print(f"  S{i} {row}")

    # 4. 分析
    print("\n[4/5] 分析市场状态...")
    stats = analyze_states(state_seq, bars, mask)
    mapping = map_states(stats)

    print(f"\n  {'状态':<10} {'笔数':<8} {'占比':<8} {'区间收益':<12} {'下根收益':<10} {'波动率'}")
    print("  " + "-" * 60)
    for s in sorted(stats.keys()):
        info = stats[s]
        label = mapping.get(s, "?")
        print(f"  S{s} [{label:<12}] {info['count']:<8} {info['pct']:>5.1f}%  "
              f"{info['mean_return']:>+8.1f}%  {info['avg_future_pct']:>+8.3f}%  "
              f"{info['volatility']:.2f}")

    # 5. 可视化
    print("\n[5/5] 生成图表...")
    plot_result(bars, mask, state_seq, stats, mapping)

    print("\n" + "=" * 60)
    print("  HMM 训练完成!")
    print("=" * 60)


# ═══════════════════════════════════════════
# 7. 模型持久化 + 实时预测 (供面板调用)
# ═══════════════════════════════════════════

import pickle

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hmm_model.pkl")


def train_and_save(symbol="XAUUSD", n_states=3):
    """训练HMM并保存模型"""
    bars = fetch_mt5_h4(symbol)
    if not bars:
        return None

    # 用精简特征集 (5维: ATR%, EMA偏差, BB宽, ROC5, ROC20)
    cl = np.array([b.close for b in bars])
    hi = np.array([b.high for b in bars])
    lo = np.array([b.low for b in bars])
    n = len(bars)

    # ATR(14)
    atr_vals = np.full(n, np.nan)
    for i in range(14, n):
        tr = [max(hi[j]-lo[j], abs(hi[j]-cl[j-1]), abs(lo[j]-cl[j-1]))
              for j in range(i-13, i+1)]
        atr_vals[i] = np.mean(tr)

    feat = np.full((n, 5), np.nan)
    for i in range(20, n):
        f = [
            float(atr_vals[i] / cl[i] * 100),
            float((cl[i] / (sum(cl[i-j]*0.9**j for j in range(20))/sum(0.9**j for j in range(20))) - 1) * 100),
            float(np.std(cl[i-19:i+1]) / np.mean(cl[i-19:i+1]) * 100),
            float((cl[i] / cl[max(0, i-5)] - 1) * 100),
            float((cl[i] / cl[max(0, i-20)] - 1) * 100),
        ]
        feat[i] = f

    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from hmmlearn import hmm as hmmlearn_hmm

    mask = ~np.isnan(feat).any(axis=1)
    X = feat[mask]
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)

    km = KMeans(n_clusters=n_states, random_state=42, n_init=10)
    kl = km.fit_predict(X_s)
    init_prob = np.bincount(kl, minlength=n_states) / len(kl)
    tm = np.zeros((n_states, n_states))
    for i in range(len(kl)-1):
        tm[kl[i], kl[i+1]] += 1
    for i in range(n_states):
        tm[i] = tm[i] / tm[i].sum() if tm[i].sum() > 0 else 1.0 / n_states

    model = hmmlearn_hmm.GaussianHMM(n_states, "diag", n_iter=100, random_state=42, init_params="")
    model.startprob_ = init_prob
    model.transmat_ = tm
    model.means_ = km.cluster_centers_
    model.covars_ = np.array([np.var(X_s[kl==i], axis=0) + 0.05 for i in range(n_states)])
    model.fit(X_s)

    # 状态映射
    seq = model.predict(X_s)
    ct = cl[mask]
    state_info = {}
    for s in range(n_states):
        idx = seq == s
        cnt = int(idx.sum())
        rets = [float((ct[i+5]/ct[i]-1)*100) for i in np.where(idx)[0] if i < len(ct)-5]
        state_info[s] = {
            "count": cnt,
            "pct": cnt / len(seq) * 100,
            "avg_future": float(np.mean(rets)) if rets else 0,
            "vol": float(np.std(np.diff(ct[idx])/ct[idx][:-1]*100) if cnt > 1 else 0),
            "self_prob": float(model.transmat_[s, s]),
        }

    # 保存
    data = {
        "model": model, "scaler": scaler,
        "symbol": symbol, "n_states": n_states,
        "state_info": state_info,
        "trained_at": datetime.datetime.now().isoformat(),
        "bars_count": len(bars),
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(data, f)
    print(f"模型已保存: {MODEL_PATH}")
    return data


def load_model():
    """加载训练好的HMM模型"""
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_current_state(symbol="XAUUSD"):
    """预测当前市场状态 (给面板调用)
    返回: {"state": 0/1/2, "label": "强势/整理/回撤", "confidence": 0.85}
    """
    data = load_model()
    if not data:
        return {"state": -1, "label": "未训练", "confidence": 0}

    model = data["model"]
    scaler = data["scaler"]

    # 获取最新 H4 K线 (面板已初始化 MT5, 不重复 init/shutdown)
    import MetaTrader5 as mt5_local
    initialized_here = False
    if not mt5_local.terminal_info():
        # MT5 未初始化时才初始化
        mp = r"C:\Program Files\MetaTrader 5\terminal64.exe"
        if not mt5_local.initialize(path=mp):
            return {"state": -1, "label": "MT5错误", "confidence": 0}
        initialized_here = True

    rates = mt5_local.copy_rates_from_pos(symbol, mt5_local.TIMEFRAME_H4, 0, 300)
    if rates is None or len(rates) < 50:
        if initialized_here:
            mt5_local.shutdown()
        return {"state": -1, "label": "数据不足", "confidence": 0}

    cl = np.array([r[4] for r in rates])
    hi = np.array([r[2] for r in rates])
    lo = np.array([r[3] for r in rates])

    # 计算最新一根的特征
    atr_vals = []
    for i in range(14, len(cl)):
        tr = [max(hi[j]-lo[j], abs(hi[j]-cl[j-1]), abs(lo[j]-cl[j-1]))
              for j in range(i-13, i+1)]
        atr_vals.append(np.mean(tr))

    i = len(cl) - 1
    atr = atr_vals[-1] if atr_vals else cl[i] * 0.005
    ema = sum(cl[i-j]*0.9**j for j in range(20))/sum(0.9**j for j in range(20)) if i >= 19 else cl[i]
    bb_std = np.std(cl[max(0,i-19):i+1])
    bb_ma = np.mean(cl[max(0,i-19):i+1])

    feat = np.array([[
        float(atr / cl[i] * 100),
        float((cl[i] / ema - 1) * 100),
        float(bb_std / bb_ma * 100 if bb_ma > 0 else 0),
        float((cl[i] / cl[max(0,i-5)] - 1) * 100),
        float((cl[i] / cl[max(0,i-20)] - 1) * 100),
    ]])
    feat_s = scaler.transform(feat)
    state = int(model.predict(feat_s)[0])
    prob = float(np.max(model.predict_proba(feat_s)[0]))

    if initialized_here:
        mt5_local.shutdown()

    # 状态映射
    info = data["state_info"].get(state, {})
    avg_future = info.get("avg_future", 0)
    vol = info.get("vol", 0)

    if avg_future > 0.08 and vol < 1.0:
        label = "📈 强势趋势"
    elif vol > 1.0:
        label = "📉 高波回撤"
    else:
        label = "📊 窄幅整理"

    return {
        "state": state,
        "label": label,
        "confidence": prob,
        "future_pct": avg_future,
        "volatility": vol,
        "self_prob": info.get("self_prob", 0),
    }


if __name__ == "__main__":
    main()
