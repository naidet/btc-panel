@echo off
chcp 65001 >nul
title BTC 交易面板

:: ================================================================
:: 智能启动器 — 有Python就用原生脚本(秒开), 没有才用EXE(慢)
:: ================================================================

cd /d "%~dp0"

:: 1. 检测 Python 是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未检测到Python, 使用EXE启动 (较慢)...
    goto USE_EXE
)

:: 2. 检测依赖是否齐全
python -c "import MetaTrader5, numpy, requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] Python依赖不完整, 使用EXE启动...
    goto USE_EXE
)

:: 3. 用 Python 原生启动 (快速)
echo [快速模式] 检测到Python, 原生启动中...
if exist "launcher.pyw" (
    :: 优先用 .pyw 版本 (无控制台窗口)
    start "" pythonw launcher.pyw 2>nul
    if %errorlevel% equ 0 goto DONE
    
    :: pythonw 不可用, 退回 python
    start "" python launcher.pyw
    if %errorlevel% equ 0 goto DONE
)

:: 回退: 直接启动面板脚本 (有控制台, 但快)
echo [快速模式] 直接启动面板...
start "" python btc_panel.py
goto DONE

:: 4. 兜底: 使用 PyInstaller EXE (解压慢, 但无需Python)
:USE_EXE
if exist "BTC交易面板.exe" (
    echo [兜底模式] 启动EXE (约5-10秒解压)...
    start "" "BTC交易面板.exe"
) else (
    echo [错误] 找不到 BTC交易面板.exe
    echo 请重新安装或联系技术支持
    pause
)

:DONE
