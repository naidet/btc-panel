#!/usr/bin/env python3
"""
BTC交易面板依赖检查
检查需要安装的软件和库
"""

import sys, os, subprocess, json
import importlib

def check_python_dependency(package_name, install_name=None):
    """检查Python包依赖"""
    if install_name is None:
        install_name = package_name
    
    try:
        importlib.import_module(package_name)
        return f"✅ {package_name} (已安装)"
    except ImportError:
        return f"❌ {package_name} (需要安装: pip install {install_name})"

def check_system_software(name, path, description):
    """检查系统软件依赖"""
    if os.path.exists(path):
        return f"✅ {name} (已安装: {path})"
    else:
        return f"❌ {name} ({description})"

def main():
    print("=" * 70)
    print("BTC AI交易面板依赖检查报告")
    print("=" * 70)
    
    print("\n📦 Python库依赖:")
    print("-" * 40)
    
    dependencies = [
        # 包名, 安装名
        ("PySide6", "PySide6"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("scikit_learn", "scikit-learn"),
        ("MetaTrader5", "MetaTrader5"),
        ("matplotlib", "matplotlib"),
        ("ccxt", "ccxt"),
        ("hmmlearn", "hmmlearn"),
    ]
    
    for package, install_name in dependencies:
        print(f"  {check_python_dependency(package, install_name)}")
    
    print("\n💻 系统软件依赖:")
    print("-" * 40)
    
    software = [
        ("MetaTrader 5", "C:/Program Files/MetaTrader 5/terminal64.exe", "外汇交易平台 - 必须安装"),
        ("Python 3.8+", "python.exe", "已通过系统环境变量检查"),
    ]
    
    for name, path, desc in software:
        print(f"  {check_system_software(name, path, desc)}")
    
    # 检查Python版本
    print("\n🐍 Python环境:")
    print("-" * 40)
    print(f"  Python版本: {sys.version}")
    print(f"  工作目录: {os.getcwd()}")
    
    # 检查面板文件
    print("\n📁 面板文件:")
    print("-" * 40)
    files = [
        ("btc_panel_qt_working.py", "修复版面板"),
        ("btc_panel_qt.py", "原始面板"),
        ("btc_panel.py", "核心模块"),
        ("btc_trader.py", "交易算法"),
        ("panel_params.json", "参数配置"),
    ]
    
    for filename, description in files:
        status = "✅ 存在" if os.path.exists(filename) else "❌ 缺失"
        print(f"  {status} {filename} ({description})")
    
    print("\n🔧 安装建议:")
    print("-" * 40)
    print("1. 如果缺少Python库:")
    print("   运行: pip install PySide6 pandas numpy scipy scikit-learn matplotlib ccxt MetaTrader5")
    print("   （使用清华镜像: -i https://pypi.tuna.tsinghua.edu.cn/simple）")
    print("\n2. 如果缺少MetaTrader 5:")
    print("   从官网下载安装: https://www.metatrader5.com/zh/download")
    print("   或者使用您的券商提供的MT5客户端")
    print("\n3. 面板启动方式:")
    print("   • 修复版: python btc_panel_qt_working.py")
    print("   • 原始版: python btc_panel_qt.py")
    print("\n4. 如果MT5安装位置不同:")
    print("   修改btc_panel.py中的MT5_PATH变量")
    
    print("\n" + "=" * 70)
    print("总结: 面板主要依赖Python库和MetaTrader 5交易平台")
    print("如果只使用模拟模式，可以暂时不安装MT5")
    print("=" * 70)

if __name__ == "__main__":
    main()