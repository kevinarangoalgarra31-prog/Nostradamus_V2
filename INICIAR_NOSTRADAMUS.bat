@echo off
chcp 65001 >nul
title Nostradamus V6 - Paper Trading Console
color 0B
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" "nostradamus_cli.py"
) else (
    python "nostradamus_cli.py"
)

if errorlevel 1 (
    echo.
    echo El menú terminó con un error.
    pause
)
