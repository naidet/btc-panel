"""USOIL 美原油(WTI)品种配置"""
SYMBOL = "USOIL"
DISPLAY = "美原油"
PARAMS = {
    "lot_min": 0.01,
    "sl_min": 20,
    "tp_min": 40,
    "risk_per_trade": 20,
}
STRATEGY_CFG = {
    "sl_min_pct": 0.25,
    "tp_min_pct": 0.50,
    "trail_profit_pct": 0.12,
    "trail_dist_pct": 0.08,
    "sl_atr_mult": 1.3,
    "tp_atr_mult": 2.0,
    "atr_spike_mult": 2.5,
    "max_spread_pct": 0.10,
}
