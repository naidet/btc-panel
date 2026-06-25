@echo off
chcp 65001 >nul
title BTC 交易面板 — 环境检查

echo ========================================
echo    BTC 交易面板 — 服务器环境检查
echo ========================================
echo.

set /a ERRORS=0

:: 1. 操作系统
echo [1/4] 操作系统检查...
ver
if not "%OS%"=="Windows_NT" (
    echo [FAIL] 需要 Windows 操作系统
    set /a ERRORS+=1
) else (
    echo [OK]   Windows
)

:: 2. Python
echo.
echo [2/4] Python 环境...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Python 未安装
    set /a ERRORS+=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK]   %%v
    python -c "import MetaTrader5; print('[OK]   MetaTrader5', MetaTrader5.__version__)" >nul 2>&1
    if %errorlevel% neq 0 (
        echo [WARN] MetaTrader5 模块未安装
        echo        执行: python -m pip install MetaTrader5
    )
    python -c "import numpy" >nul 2>&1 && echo [OK]   numpy || echo [WARN] numpy 未安装
    python -c "import requests" >nul 2>&1 && echo [OK]   requests || echo [WARN] requests 未安装
)

:: 3. MT5 终端
echo.
echo [3/4] MetaTrader 5 终端...
for %%p in (
    "C:\Program Files\MetaTrader 5\terminal64.exe"
    "C:\Program Files (x86)\MetaTrader 5\terminal64.exe"
    "%USERPROFILE%\AppData\Roaming\MetaQuotes\Terminal\*\terminal64.exe"
) do (
    if exist %%p (
        echo [OK]   %%p
        goto :mt5_found
    )
)
echo [WARN] 未在默认路径找到 MT5 terminal64.exe
echo        请确认 MT5 已安装, 面板启动后可在参数中配置路径
:mt5_found

:: 4. 网络
echo.
echo [4/4] 网络连接...
ping -n 1 api.binance.com >nul 2>&1 && echo [OK]   币安 API 可达 || echo [WARN] 币安 API 不可达 (吃单比模块将跳过)
ping -n 1 8.8.8.8 >nul 2>&1 && echo [OK]   网络正常 || echo [WARN] 网络可能受限

:: 总结
echo.
echo ========================================
if %ERRORS% gtr 0 (
    echo    检查完成: %ERRORS% 个问题需要处理
) else (
    echo    检查完成: 环境就绪!
)
echo ========================================
echo.
pause
