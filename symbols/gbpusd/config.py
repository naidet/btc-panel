"""GBPUSD 品种配置"""
SYMBOL = "GBPUSD"
DISPLAY = "镑美"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 0.0015,
    "tp_min": 0.003,
    "risk_per_trade": 20,
}
STRATEGY_CFG = {
    "sl_min_pct": 0.08,
    "tp_min_pct": 0.15,
    "trail_profit_pct": 0.04,
    "trail_dist_pct": 0.03,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.0,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
}
