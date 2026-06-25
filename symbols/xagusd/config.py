"""XAGUSD 白银品种配置"""
SYMBOL = "XAGUSD"
DISPLAY = "白银"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 1500,       # 白银止损约$15 ≈ 1500点 (每点$0.01)
    "tp_min": 3000,       # 白银止盈约$30 ≈ 3000点
    "risk_per_trade": 20,
}
STRATEGY_CFG = {
    "sl_min_pct": 0.3,
    "tp_min_pct": 0.6,
    "trail_profit_pct": 0.15,
    "trail_dist_pct": 0.10,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.0,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.20,
}
