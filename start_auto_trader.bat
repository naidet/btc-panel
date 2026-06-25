@echo off
title MT5 Auto Trader
cd /d "%~dp0"
echo Starting MT5 Auto Trader...
echo.
echo  Account #60107268 | RSI+EMA Daily | Risk $10
echo.
start /MIN "" "C:\Users\82682\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0mt5_auto_trader.py"
echo Running in background (PID above)
echo Log: %~dp0mt5_auto_log.txt
echo.
echo Close this window to stop monitoring.
timeout /t 5 /nobreak >nul
