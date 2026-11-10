# -*- coding: utf-8 -*-
"""desktop.py —— Echo 回声桌面应用（独立窗口，双击 exe 即用）

把网页版装进一个原生窗口，像 QQ、微信一样是个正经的桌面 App。
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
    time.sleep(1)
    import webview
    webview.create_window(
        "回声 Echo", "http://127.0.0.1:%d" % webui.PORT,
        width=960, height=720, min_size=(600, 520))
    webview.start()


if __name__ == "__main__":
    main()
