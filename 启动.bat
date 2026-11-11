@echo off
chcp 936 >nul
title Echo 回声
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
    py --version >nul 2>nul
    if errorlevel 1 (
        echo [错误] 没找到 Python，请先安装 Python 3.10+ 并勾选 Add Python to PATH
        pause
        exit /b
    )
    py echo.py
) else (
    python echo.py
)
pause
