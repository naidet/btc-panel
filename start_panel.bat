@echo off
title BTC AI 交易面板
cd /d "%~dp0"
echo Starting Data Bridge...
start "" "C:\Users\82682\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe" "%~dp0data_bridge.py"
timeout /t 2 /nobreak >nul
echo Starting Trading Panel...
start "" "C:\Users\82682\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe" "%~dp0btc_panel.py"
