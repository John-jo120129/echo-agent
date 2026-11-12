# -*- coding: utf-8 -*-
"""build_exe.py —— 一键打包 Windows 桌面版 exe

用法：python build_exe.py
产物：dist/Echo桌面/Echo桌面.exe（整个文件夹一起拷贝给用户）

为什么用 --onedir 而不是 --onefile：
  onefile 每次启动要把 300MB+ 解压到临时目录，慢；而且很多杀软会把
  "自解压再执行" 的 exe 判为可疑直接杀掉，表现为"双击闪退/服务起不来"。
  onedir 启动快、稳定、出错也看得见。
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

ICON = os.path.join(BASE, "assets", "echo.ico")

args = [
    sys.executable, "-m", "PyInstaller",
    "--onedir", "--name", "Echo桌面", "--console", "desktop.py",
    "--add-data", "persona.md;.",
    "--add-data", "config.json;.",
    "--add-data", "skills;skills",
    "--add-data", "kb;kb",
    "--add-data", "core/ocr.ps1;core",
    "--collect-submodules", "core",
    "--collect-all", "pyautogui",
    "--collect-all", "uiautomation",
    "--collect-all", "edge_tts",
    "--collect-all", "sounddevice",
    "--collect-all", "faster_whisper",
    "--collect-all", "ctranslate2",
    "--collect-all", "onnxruntime",
    "--collect-all", "playwright",
]
if os.path.isfile(ICON):
    args += ["--icon", ICON]

print("开始打包（约 2-4 分钟）...")
rc = subprocess.call(args)
if rc == 0:
    out = os.path.join(BASE, "dist", "Echo桌面")
    print("\n打包成功：%s" % out)
    print("把整个「Echo桌面」文件夹拷给别人，双击里面的 Echo桌面.exe 就能用。")
    print("注意：文件夹约 400MB（含语音识别/OCR 依赖）。")
else:
    print("\n打包失败，看上面 PyInstaller 的报错。")
sys.exit(rc)
