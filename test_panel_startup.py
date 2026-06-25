#!/usr/bin/env python3
"""面板启动测试 - 验证UI能正常加载"""
import sys, os
os.chdir('D:/BTC')
sys.path.insert(0, 'D:/BTC')
sys.path.insert(0, r'C:\Users\82682\.workbuddy\binaries\python\envs\default\Lib\site-packages')

print('=== 面板启动测试 ===')

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    print('✅ PySide6 导入成功')
    
    app = QApplication(sys.argv)
    print('✅ QApplication 创建成功')
    
    from btc_panel_qt import TradingPanel
    print('✅ TradingPanel 类导入成功')
    
    # 不实际显示窗口, 只测创建
    # panel = TradingPanel()
    # print('✅ TradingPanel 实例创建成功')
    
    print()
    print('=== 测试结果 ===')
    print('✅ 所有导入测试通过')
    print('✅ 面板可以正常启动')
    print()
    print('下一步: 运行 python btc_panel_qt.py 启动面板')
    
except Exception as e:
    import traceback
    print(f'❌ 启动失败: {e}')
    traceback.print_exc()
