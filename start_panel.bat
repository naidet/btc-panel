@echo off
chcp 65001 >nul
echo 正在启动 BTC AI 交易面板...
echo.

cd /d "D:\BTC"

python btc_panel_qt.py

if %errorlevel% neq 0 (
    echo.
    echo 面板启动失败，错误代码: %errorlevel%
    pause
) else (
    echo.
    echo 面板已正常关闭
    pause
)