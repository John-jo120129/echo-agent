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


def _start_server():
    srv = ThreadingHTTPServer((webui.HOST, webui.PORT), webui.Handler)
    srv.serve_forever()


def main():
    threading.Thread(target=_start_server, daemon=True).start()
    time.sleep(1.5)
    url = "http://127.0.0.1:%d" % webui.PORT
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
