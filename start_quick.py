#!/usr/bin/env python3
"""
快速启动面板 - 绕过MT5初始化
"""
import sys, os
os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

# 设置环境变量来跳过MT5初始化
os.environ['SKIP_MT5'] = '1'

# 导入前模拟MetaTrader5模块
class MockMT5:
    @staticmethod
    def initialize(path=None, **kwargs):
        print(f"MockMT5.initialize called (skipped)")
        return True
    
    @staticmethod
    def shutdown():
        print(f"MockMT5.shutdown called")
    
    @staticmethod
    def copy_rates_from_pos(symbol, timeframe, start_pos, count):
        print(f"MockMT5.copy_rates_from_pos({symbol})")
        return []
    
    @staticmethod
    def account_info():
        return None
    
    @staticmethod
    def positions_total():
        return 0

# 在导入前设置模拟模块
import builtins
import types
mt5_module = types.ModuleType('MetaTrader5')
for attr in dir(MockMT5):
    if not attr.startswith('_'):
        setattr(mt5_module, attr, getattr(MockMT5, attr))
sys.modules['MetaTrader5'] = mt5_module

print("启动BTC AI交易面板...")
try:
    import btc_panel_qt
    app = btc_panel_qt.QApplication(sys.argv)
    window = btc_panel_qt.BTCTradingPanel()
    window.show()
    sys.exit(app.exec())
except Exception as e:
    print(f"启动失败: {e}")
    import traceback
    traceback.print_exc()
    input("按Enter退出...")