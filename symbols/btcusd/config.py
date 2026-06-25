"""BTCUSD 品种配置"""
SYMBOL = "BTCUSD"
DISPLAY = "BTC"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 800,
    "tp_min": 1500,
    "risk_per_trade": 20,
}
# 策略配置 (回测用)
STRATEGY_CFG = {
    "sl_min_pct": 0.8,
    "tp_min_pct": 1.5,
    "trail_profit_pct": 0.3,
    "trail_dist_pct": 0.2,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.0,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
}
