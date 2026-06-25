@echo off
chcp 65001 >nul
title BTC 交易面板 v3 — 智能部署

echo ╔══════════════════════════════════════════════╗
echo ║    BTC AI 交易面板 v3   智能部署工具        ║
echo ╚══════════════════════════════════════════════╝
echo.

set "MT5_GUESS="
set "NEED_MT5=0"

:: ========================================
:: Step 1: 检测 MetaTrader 5 是否已安装
:: ========================================
echo [1/4] 检测 MetaTrader 5...

for %%p in (
    "C:\Program Files\MetaTrader 5\terminal64.exe"
    "C:\Program Files (x86)\MetaTrader 5\terminal64.exe"
    "D:\MetaTrader 5\terminal64.exe"
) do (
    if exist %%p (
        set "MT5_GUESS=%%~p"
        goto :mt5_ok
    )
)

:: 没找到, 搜索用户目录
for /d %%d in ("%USERPROFILE%\AppData\Roaming\MetaQuotes\Terminal\*") do (
    if exist "%%d\terminal64.exe" (
        set "MT5_GUESS=%%d\terminal64.exe"
        goto :mt5_ok
    )
)

:: 没找到 → 提示下载
set "NEED_MT5=1"
echo.
echo  ⚠  未检测到 MetaTrader 5
echo.
echo  ┌─────────────────────────────────────────┐
echo  │  MT5 下载地址:                           │
echo  │  https://www.metatrader5.com/download    │
echo  │                                         │
echo  │  安装后登录你的交易账户                │
echo  │  然后重新运行本脚本继续部署              │
echo  └─────────────────────────────────────────┘
echo.
echo  按任意键打开下载页面...
pause >nul
start https://www.metatrader5.com/download
echo.
echo  下载安装 MT5 后, 重新运行本脚本。
echo.
pause
exit /b 0

:mt5_ok
echo  [OK] 已找到: %MT5_GUESS%
echo.

:: ========================================
:: Step 2: 检查 Python 环境
:: ========================================
echo [2/4] 检查 Python 环境...

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [FAIL] Python 未安装
    echo.
    echo  下载: https://www.python.org/downloads/
    echo  安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo  [OK]  %%v

:: ========================================
:: Step 3: 安装 Python 依赖
:: ========================================
echo [3/4] 安装 Python 依赖...

echo   MetaTrader5...
python -m pip install MetaTrader5 --quiet 2>nul
if %errorlevel%==0 (echo    [OK]) else (echo    [FAIL] 请手动执行: pip install MetaTrader5)

echo   numpy...
python -m pip install numpy --quiet 2>nul
if %errorlevel%==0 (echo    [OK]) else (echo    [FAIL])

echo   requests...
python -m pip install requests --quiet 2>nul
if %errorlevel%==0 (echo    [OK]) else (echo    [FAIL])

:: ========================================
:: Step 4: 创建桌面快捷方式
:: ========================================
echo [4/4] 创建快捷方式...

set "DESKTOP=%USERPROFILE%\Desktop"
set "START_BAT=%~dp0start_btc.bat"

if exist "%START_BAT%" (
    powershell -NoProfile -Command ^
        "$ws = New-Object -ComObject WScript.Shell; ^
         $s = $ws.CreateShortcut('%DESKTOP%\BTC交易面板.lnk'); ^
         $s.TargetPath = '%START_BAT%'; ^
         $s.WorkingDirectory = '%~dp0'; ^
         $s.WindowStyle = 7; ^
         $s.Description = 'BTC AI 交易面板 — 智能启动 (有Python秒开)'; ^
         $s.Save()" 2>nul
    if exist "%DESKTOP%\BTC交易面板.lnk" (
        echo  [OK] 桌面快捷方式: BTC交易面板.lnk
    ) else (
        echo  [WARN] 快捷方式创建失败, 请手动创建
    )
) else (
    echo  [WARN] 未找到 start_btc.bat
    echo        请确保部署文件完整
)

:: ========================================
:: 完成
:: ========================================
echo.
echo ╔══════════════════════════════════════════════╗
echo ║            部署完成!                        ║
echo ╚══════════════════════════════════════════════╝
echo.
echo  MT5 路径: %MT5_GUESS%
echo.
echo  下一步:
echo    1. 打开 MetaTrader 5, 登录你的交易账户
echo    2. 双击桌面 "BTC交易面板" 启动
echo    3. 在面板中点击 "启动自动交易"
echo.
echo  注意事项:
echo    - MT5 必须保持运行, 不能关闭
echo    - 服务器不要设置休眠
echo    - RDP断开后MT5仍运行 (不要注销用户)
echo.
pause
