# -*- coding: utf-8 -*-
"""core/browser.py —— 浏览器自动化（Playwright）

网页操控的双手：
  browser_open       打开网页
  browser_read       读当前页面的文字内容
  browser_click      点击元素（文本或 CSS 选择器）
  browser_type       在输入框填文字
  browser_screenshot 截当前页面

可视化 / 隐藏：
  复用 stealth 开关——隐藏模式 = 无头浏览器（后台跑，不弹窗，真正"隐藏"）；
  可视化模式 = 有头浏览器（能亲眼看到它操作）。

默认用系统自带的 Edge（channel=msedge），不用额外下载浏览器。
"""
import os

# 懒加载，没装 playwright 时 import 不报错
_pw = None
_page = None
_browser = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_TMP = os.path.join(BASE_DIR, "data", "_page.png")

ctx = {"stealth": False}


def _get_page(headless=None):
    global _pw, _page, _browser
    if _pw is None:
        try:
            from playwright.sync_api import sync_playwright
            _pw = sync_playwright().start()
        except Exception as e:
            raise RuntimeError(
                "Playwright 没装好：pip install playwright。详情：%s" % e)
    if headless is None:
        headless = ctx["stealth"]
    if _page is None or _page.is_closed():
        # 优先系统 Edge，退回系统 Chrome
        for channel in ("msedge", "chrome"):
            try:
                _browser = _pw.chromium.launch(channel=channel, headless=headless)
                _page = _browser.new_page()
                break
            except Exception:
                _browser = None
        if _browser is None:
            raise RuntimeError("找不到系统 Edge/Chrome，或需 playwright install")
    return _page


def browser_open(url, headless=None):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    page = _get_page(headless)
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    return "已打开 %s\n页面标题：%s" % (url, page.title())


def browser_read(maxlen=4000):
    page = _get_page()
    try:
        text = page.inner_text("body")
    except Exception:
        text = page.content()
        import re
        text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text[:maxlen] or "（页面没读到文字）"


def browser_click(target):
    page = _get_page()
    target = target.strip()
    # 含 CSS 特征按选择器，否则按可见文本点
    if any(c in target for c in ".#[>=") or " " in target:
        page.locator(target).first.click(timeout=10000)
    else:
        page.get_by_text(target, exact=False).first.click(timeout=10000)
    return "已点击：%s" % target


def browser_type(selector, text):
    page = _get_page()
    page.locator(selector).first.fill(text)
    return "已在 %s 输入：%s" % (selector, text)


def browser_press(key):
    page = _get_page()
    page.keyboard.press(key)
    return "已按键：" + key


def browser_screenshot(path=None):
    page = _get_page()
    path = path or SHOT_TMP
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.screenshot(path=path)
    return "已截当前页面到 %s" % path


def browser_close():
    global _page, _browser
    if _browser:
        try:
            _browser.close()
        except Exception:
            pass
    _browser = None
    _page = None
    return "已关闭浏览器"
