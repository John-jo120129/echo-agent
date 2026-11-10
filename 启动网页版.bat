@echo off
chcp 65001 >nul
title Echo Web
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python webui.py
) else (
    "C:\Users\jiangchengzhi\AppData\Local\Programs\Python\Python311\python.exe" webui.py
)
pause
