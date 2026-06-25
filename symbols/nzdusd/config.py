"""NZDUSD 纽元/美元品种配置"""
SYMBOL = "NZDUSD"
DISPLAY = "纽美"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 6,
    "tp_min": 12,
    "risk_per_trade": 20,
}
STRATEGY_CFG = {
    "sl_min_pct": 0.20,
    "tp_min_pct": 0.40,
    "trail_profit_pct": 0.10,
    "trail_dist_pct": 0.08,
    "sl_atr_mult": 1.3,
    "tp_atr_mult": 2.0,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
}
