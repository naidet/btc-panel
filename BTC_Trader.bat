@echo off
title BTC Trading Web Panel
echo ========================================
echo   BTC Trading Robot v1.0
echo   Opening Web Panel...
echo ========================================
echo.
echo  Starting server, please wait...
echo  Web panel will open automatically.
echo.
"C:\Users\82682\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0btc_trader.py" --server
pause
