@echo off
title Ascent
cd /d "%~dp0"

:: Prefer the project .venv (setup.ps1 creates it); fall back to pythonw on PATH.
set PYW=%~dp0.venv\Scripts\pythonw.exe
if not exist "%PYW%" set PYW=pythonw

:: `ascent.bat --demo`: the fictional demo instance (demo\ folder, port 5002).
:: app.py seeds it on first run and never reuses the instance on 5001.
if /i "%~1"=="--demo" (
    start "" "%PYW%" "%~dp0app.py" --demo
    exit /b 0
)

:: Already running? Just open the UI.
netstat -aon | findstr ":5001 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    start "" msedge --app=http://127.0.0.1:5001 --window-size=1400,900
    exit /b 0
)

:: Launch pywebview app (windowed).
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
    start "" msedge --app=http://127.0.0.1:5001 --window-size=1400,900
    exit /b 1
)

:: Give pywebview 3s to render window; if not, open browser anyway
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq msedgewebview2.exe" 2>nul | findstr /I "msedgewebview2" >nul
if errorlevel 1 (
    start "" msedge --app=http://127.0.0.1:5001 --window-size=1400,900
)
exit /b 0
