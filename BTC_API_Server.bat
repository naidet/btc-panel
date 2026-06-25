@echo off
title BTC Signal Server
echo ========================================
echo   BTC Signal Server Starting...
echo   For MT5: Load BTC_Signal_EA.mq5
echo ========================================
echo.
echo  Starting, please wait...
echo.
"C:\Users\82682\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0btc_trader.py" --server
pause
