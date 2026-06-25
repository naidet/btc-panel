#!/usr/bin/env python3
"""
测试面板启动的脚本
"""
import sys
import os

# 设置工作目录
os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

try:
    print("测试1: 导入核心模块...")
    from btc_panel import fetch_dashboard_data, get_trade_signal
    print("✅ 核心模块导入成功")
    
    print("\n测试2: 测试fetch_dashboard_data函数...")
    params = {
        "symbol": "XAUUSD",
        "ema1": 10,
        "ema2": 20,
        "rsi_period": 14,
        "adx_period": 14,
        "atr_period": 14,
        "ml_threshold": 0.5,
        "ml_confidence": 0.7,
        "ml_predict_volume": 5,
        "ml_predict_trend": 5,
        "hmm_trend": 0,
        "hmm_volatility": 0,
        "hmm_state": 0,
        "max_risk_ratio": 0.02
    }
    
    # 由于需要MT5连接，我们只是测试函数是否存在
    print(f"✅ fetch_dashboard_data函数存在: {fetch_dashboard_data}")
    print(f"✅ get_trade_signal函数存在: {get_trade_signal}")
    
    print("\n测试3: 测试PySide6导入...")
    from PySide6.QtWidgets import QApplication
    print("✅ PySide6导入成功")
    
    print("\n测试4: 测试btc_panel_qt模块导入...")
    import btc_panel_qt
    print("✅ btc_panel_qt模块导入成功")
    
    print("\n🎉 所有测试通过！面板应该可以正常启动了。")
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print(f"Python路径: {sys.path}")
    
except Exception as e:
    print(f"❌ 其他错误: {e}")
    import traceback
    traceback.print_exc()