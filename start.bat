@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set PYTHON_CMD=
where py >nul 2>&1 && set PYTHON_CMD=py
if not defined PYTHON_CMD where python >nul 2>&1 && set PYTHON_CMD=python

if not defined PYTHON_CMD (
    echo [CHYBA] Python nenalezen! Spustte nejdrive setup.bat
    pause
    exit /b 1
)

!PYTHON_CMD! app.py
