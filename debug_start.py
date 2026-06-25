#!/usr/bin/env python3
"""
调试启动脚本 - 捕获所有可能的错误
"""
import sys
import os
import traceback
import logging

# 设置详细的日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

os.chdir("D:/BTC")
sys.path.insert(0, "D:/BTC")

def test_imports():
    """测试所有必要的导入"""
    imports_to_test = [
        ("PySide6", "from PySide6.QtWidgets import QApplication, QMainWindow"),
        ("MetaTrader5", "import MetaTrader5 as mt5"),
        ("btc_panel", "from btc_panel import fetch_dashboard_data, get_trade_signal"),
        ("numpy", "import numpy as np")
    ]
    
    for name, import_stmt in imports_to_test:
        try:
            logging.info(f"测试导入: {name}")
            exec(import_stmt, globals())
            logging.info(f"✅ {name} 导入成功")
        except ImportError as e:
            logging.error(f"❌ {name} 导入失败: {e}")
            return False
    return True

def test_main_window():
    """测试主窗口创建"""
    try:
        logging.info("测试主窗口创建...")
        
        # 导入必要的组件
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        
        # 创建应用
        app = QApplication([])
        
        # 导入MainWindow类
        from btc_panel_qt import MainWindow
        
        logging.info("创建MainWindow实例...")
        window = MainWindow()
        
        # 设置定时器来检查窗口并退出
        def close_app():
            logging.info("✅ 窗口创建成功，正在退出测试...")
            window.close()
            app.quit()
        
        QTimer.singleShot(500, close_app)
        
        logging.info("进入事件循环...")
        return app.exec()
        
    except Exception as e:
        logging.error(f"❌ 主窗口测试失败: {e}")
        traceback.print_exc()
        return False

def main():
    print("=== BTC 交易面板调试启动 ===\n")
    
    # 测试导入
    if not test_imports():
        print("\n❌ 导入测试失败，请检查依赖")
        return 1
    
    # 测试主窗口
    print("\n=== 测试主窗口创建 ===")
    try:
        result = test_main_window()
        if result == 0:
            print("\n✅ 所有测试通过！面板应该可以正常运行了。")
        else:
            print(f"\n⚠️  应用退出代码: {result}")
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())