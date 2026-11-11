# -*- coding: utf-8 -*-
"""install.py —— Echo 一键安装（Windows / macOS / Linux 通用）

装依赖 → 查 Ollama → 可选拉模型。
比 .bat 稳：不受控制台编码、换行影响。
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PACKAGES = [
    "pyautogui", "uiautomation", "playwright",
    "faster-whisper", "sounddevice", "edge-tts", "requests",
]
MODELS = ["qwen2.5:7b", "mxbai-embed-large", "qwen2.5vl:7b"]


def run(cmd, timeout=600):
    print("  $ " + " ".join(cmd))
    try:
        return subprocess.call(cmd, timeout=timeout)
    except Exception as e:
        print("  执行失败：%s" % e)
        return 1


def main():
    print("=" * 52)
    print("  Echo 回声 · 一键安装")
    print("=" * 52)
    print("  Python：%s" % sys.version.split()[0])

    # 1. 依赖
    print("\n[1/4] 安装 Python 依赖（首次约 3-8 分钟）...")
    ok = run([sys.executable, "-m", "pip", "install", "-q",
              "--upgrade"] + PACKAGES, timeout=900)
    if ok == 0:
        print("      依赖装好了")
    else:
        print("      有依赖没装上，可以先手动跑：pip install " + " ".join(PACKAGES))

    # 2. Ollama
    print("\n[2/4] 检查 Ollama ...")
    exe = "ollama.exe" if os.name == "nt" else "ollama"
    has_ollama = subprocess.call([exe, "--version"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL) == 0
    if has_ollama:
        print("      Ollama 已安装")
    else:
        print("      [未找到] 请先到 https://ollama.com 下载安装 Ollama，装完重开本脚本")
        print("      （装好后本脚本可以再跑一次，只补模型）")

    # 3. 模型
    print("\n[3/4] 下载模型（体积较大，可跳过）")
    print("      大脑(必装)   : qwen2.5:7b       约 4.7G")
    print("      知识库向量   : mxbai-embed-large 约 0.7G")
    print("      看图/视频    : qwen2.5vl:7b     约 6G（可选）")
    try:
        ans = input("\n      现在自动下载吗？(y/n): ").strip().lower()
    except EOFError:
        ans = "n"
    if ans == "y" and has_ollama:
        for m in MODELS:
            print("\n      正在拉 %s ..." % m)
            run([exe, "pull", m], timeout=7200)
    elif ans == "y" and not has_ollama:
        print("      跳过：Ollama 还没装")
    else:
        print("      跳过。以后可以手动跑：ollama pull qwen2.5:7b")

    # 4. 完成
    print("\n[4/4] 完成！")
    print("      双击「启动.bat」      → 命令行版")
    print("      双击「启动网页版.bat」→ 网页版（浏览器里聊）")
    print("      第一次用网页版若报缺浏览器内核，跑一次：python -m playwright install chromium")
    print("\n" + "=" * 52)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
    input("\n按回车退出...")
