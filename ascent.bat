@echo off
title Ascent
cd /d "%~dp0"

:: Already running? Just open the UI.
netstat -aon | findstr ":5001 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    start "" msedge --app=http://localhost:5001 --window-size=1400,900
    exit /b 0
)

:: Launch pywebview app (windowed). Prefer the project .venv: its site-packages
:: sit on a normal path instead of the virtualized, Defender-scanned WindowsApps
:: store, and it has flask-compress (Store Python doesn't, so gzip was silently off).
set PYW=%~dp0.venv\Scripts\pythonw.exe
if not exist "%PYW%" set PYW=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\pythonw.exe
start "" "%PYW%" "%~dp0app.py"

:: Fallback: wait for port, then open in browser if pywebview window not showing
set /a tries=0
:wait
timeout /t 1 /nobreak >nul
set /a tries+=1
netstat -aon | findstr ":5001 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    if %tries% lss 12 goto wait
    echo Flask failed to start within 12s
    start "" msedge --app=http://localhost:5001 --window-size=1400,900
    exit /b 1
)

:: Give pywebview 3s to render window; if not, open browser anyway
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq msedgewebview2.exe" 2>nul | findstr /I "msedgewebview2" >nul
if errorlevel 1 (
    start "" msedge --app=http://localhost:5001 --window-size=1400,900
)
exit /b 0
