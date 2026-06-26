"""XAUUSD 黄金品种配置"""
SYMBOL = "XAUUSD"
DISPLAY = "黄金"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 1200,       # 黄金止损 ~0.3% ≈ $12@4000 (BTGT point=0.01)
    "tp_min": 2400,       # 黄金止盈 ~0.6% ≈ $24@4000 (BTGT point=0.01)
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
    "max_spread_pct": 0.15,
}
