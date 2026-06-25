"""NAS100 纳斯达克指数品种配置"""
SYMBOL = "NAS100"
DISPLAY = "纳指"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 60,
    "tp_min": 120,
    "risk_per_trade": 20,
}
STRATEGY_CFG = {
    "sl_min_pct": 0.15,
    "tp_min_pct": 0.30,
    "trail_profit_pct": 0.10,
    "trail_dist_pct": 0.05,
    "sl_atr_mult": 1.2,
    "tp_atr_mult": 2.0,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.10,
}
