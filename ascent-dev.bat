@echo off
title Ascent (dev — live reload)
cd /d "%~dp0"

:: Live-reload dev mode: Flask API on 5001 + Vite dev server on 5173 with HMR.
:: Edit anything under frontend\src and the window updates instantly — no rebuild.
:: Uses console python (not pythonw) so Vite/HMR logs are visible in this window.

set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" set PY=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe
if not exist "%PY%" set PY=python

"%PY%" "%~dp0app.py" --dev
pause
