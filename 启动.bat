@echo off
chcp 65001 >nul
title Echo
cd /d "%~dp0"
set PY="C:\Users\jiangchengzhi\AppData\Local\Programs\Python\Python311\python.exe"
if exist %PY% (
    %PY% echo.py
) else (
    python echo.py
)
pause
