@echo off
chcp 65001 >nul
title Echo Agent
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python echo.py
) else (
    "C:\Users\jiangchengzhi\AppData\Local\Programs\Python\Python311\python.exe" echo.py
)
pause
