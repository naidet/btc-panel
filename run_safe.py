#!/usr/bin/env python3
"""
安全启动脚本 - 捕获所有异常并显示错误信息
"""
import sys
import os
import traceback
import time

def main():
    print("=" * 60)
    print("BTC AI 交易面板 - 安全启动模式")
    print("=" * 60)
    print()
    
    # 设置工作目录
    try:
        os.chdir("D:/BTC")
        sys.path.insert(0, "D:/BTC")
        print("✅ 工作目录设置成功")
    except Exception as e:
        print(f"❌ 设置工作目录失败: {e}")
        input("按Enter键退出...")
        return 1
    
    # 测试环境
    print("\n[1/3] 测试环境...")
    try:
        import importlib
        required_modules = [
            ("PySide6", "PySide6"),
            ("MetaTrader5", "MetaTrader5"),
            ("numpy", "numpy"),
            ("matplotlib", "matplotlib")
        ]
        
        for name, module in required_modules:
            try:
                importlib.import_module(module)
                print(f"  ✅ {name} 可用")
            except ImportError:
                print(f"  ⚠️  {name} 未安装或导入失败")
        
    except Exception as e:
        print(f"❌ 环境测试失败: {e}")
    
    # 导入模块
    print("\n[2/3] 导入模块...")
    try:
        from btc_panel import fetch_dashboard_data, get_trade_signal
        print("  ✅ 核心交易模块导入成功")
    except ImportError as e:
        print(f"  ❌ 核心模块导入失败: {e}")
        print(f"  Python路径: {sys.path}")
        input("按Enter键退出...")
        return 1
    
    # 启动应用
    print("\n[3/3] 启动应用...")
    print("  正在初始化GUI，请稍候...")
    
    try:
        from PySide6.QtWidgets import QApplication
        from btc_panel_qt import main as qt_main
        
        print("  ✅ GUI模块导入成功")
        print("  ⏳ 正在启动主窗口...")
        
        # 直接调用主函数
        qt_main()
        
    except Exception as e:
        print(f"\n❌ 启动失败!")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print("\n详细堆栈跟踪:")
        traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("建议的解决方案:")
        print("1. 检查Python依赖是否完整安装")
        print("2. 检查MetaTrader5是否已安装")
        print("3. 检查工作目录和文件权限")
        print("=" * 60)
        
        input("\n按Enter键退出...")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 未处理的异常: {e}")
        traceback.print_exc()
        input("\n按Enter键退出...")
        sys.exit(1)