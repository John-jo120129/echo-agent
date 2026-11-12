# -*- coding: utf-8 -*-
"""desktop.py —— Echo 回声桌面版入口（双击 exe 即用）

启动后自动起本地服务并打开默认浏览器，稳定不闪退。
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import ThreadingHTTPServer

import webui   # 复用网页版的 Handler / HOST / PORT

# exe 打包后 __file__ 在临时目录，日志要落到 exe 旁边才能找到
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(APP_DIR, "data", "desktop.log")


def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _start_server():
    try:
        srv = ThreadingHTTPServer((webui.HOST, webui.PORT), webui.Handler)
        _log("服务已监听 %s:%d" % (webui.HOST, webui.PORT))
        srv.serve_forever()
    except Exception as e:
        _log("服务启动失败: %s" % e)
        print("=" * 46)
        print("  [错误] 网页服务启动失败：%s" % e)
        print("  常见原因：端口 %d 被占用，或防火墙拦截。" % webui.PORT)
        print("  可以先用 taskkill 关掉占用端口的进程，或改 webui.py 的 PORT。" % webui.PORT)
        print("=" * 46)
        # 不退出主线程，让窗口留着看得到错误


def main():
    _log("=== 启动 === frozen=%s cwd=%s" % (getattr(sys, "frozen", False), os.getcwd()))
    threading.Thread(target=_start_server, daemon=True).start()
    time.sleep(1.5)
    url = "http://127.0.0.1:%d" % webui.PORT
    # 调试时设 ECHO_NO_BROWSER=1 就不自动开浏览器，避免反复弹窗
    if not os.environ.get("ECHO_NO_BROWSER"):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    print("=" * 46)
    print("  Echo 回声已启动，浏览器已自动打开：%s" % url)
    print("  关闭本窗口即退出。")
    print("=" * 46)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
