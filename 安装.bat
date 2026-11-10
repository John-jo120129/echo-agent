@echo off
chcp 65001 >nul
title Echo 回声 - 一键安装
echo.
echo   ========================================
echo     Echo 回声 · 一键安装
echo   ========================================
echo.

echo   [1/4] 安装 Python 依赖库...
python -m pip install -q pyautogui uiautomation playwright faster-whisper sounddevice edge-tts
echo         依赖安装完成

echo   [2/4] 检查 Ollama（本地大模型运行器）...
where ollama >nul 2>nul
if %errorlevel%==0 (
    echo         Ollama 已安装
) else (
    echo         [未找到] 请先到 https://ollama.com 下载安装 Ollama
)

echo   [3/4] 下载模型（体积较大，可先跳过）
echo         默认大脑(必装)  : qwen2.5:7b
echo         知识库检索(必装): mxbai-embed-large
echo         看图/视频(可选) : qwen2.5vl:7b
echo.
set /p DL=         现在自动下载模型吗？(y/n):
if /i "%DL%"=="y" (
    ollama pull qwen2.5:7b
    ollama pull mxbai-embed-large
    ollama pull qwen2.5vl:7b
    ollama create qwen2.5vl-16k -f Modelfile.vl
)

echo.
echo   [4/4] 完成！
echo         双击「启动.bat」开始用（命令行）
echo         或双击「启动网页版.bat」用网页版
echo.
pause
