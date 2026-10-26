@echo off
title Moorttys Voice - YouTube + TikTok LIVE
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Python no se encontro. Instala Python 3 desde https://www.python.org/downloads/
    pause
    exit /b 1
)
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py main.py
if errorlevel 1 pause
