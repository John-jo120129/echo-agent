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


def browser_get_elements(max_items=40):
    """列出页面上可交互的元素（文字 + 标签 + id），让模型"看见"页面结构。

    这就是"DOM 感知"：比截图省 token、定位更准；DOM 拿不到时再用 view_screen 兜底。
    """
    page = _get_page()
    js = """() => {
      const els = [...document.querySelectorAll(
        'a,button,input,textarea,select,[role=button],[onclick]')];
      const out = [];
      for (const e of els) {
        const text = (e.innerText || e.value || e.placeholder || e.name || '').trim();
        const rect = e.getBoundingClientRect();
        if (!text || rect.width === 0 || rect.height === 0) continue;
        out.push({
          tag: e.tagName.toLowerCase(),
          text: text.slice(0, 40),
          id: e.id || '',
          cls: (typeof e.className === 'string' ? e.className : '').slice(0, 30),
          x: Math.round(rect.left + rect.width / 2),
          y: Math.round(rect.top + rect.height / 2),
          visible: rect.top >= 0 && rect.top < window.innerHeight
        });
      }
      return out.slice(0, 80);
    }"""
    try:
        items = page.evaluate(js)
    except Exception as e:
        return "读不到页面元素：%s" % e
    if not items:
        return "页面上没找到可点元素（可能是纯 Canvas 或还没加载完）"
    lines = []
    for it in items[:max_items]:
        hint = ""
        if it["id"]:
            hint += " #" + it["id"]
        lines.append("- <%s> 「%s」%s @(%d,%d)%s" % (
            it["tag"], it["text"], hint, it["x"], it["y"],
            "" if it["visible"] else "（需滚动）"))
    return "页面可交互元素（%d 个）：\n%s" % (len(items), "\n".join(lines))


def browser_click(target):
    """点击：CSS 选择器 → 可见文本 → 按钮角色，三层兜底（混合感知）。"""
    page = _get_page()
    target = target.strip()
    errors = []
    # 策略 1：CSS 选择器
    if any(c in target for c in ".#[>=") or " " in target:
        try:
            page.locator(target).first.click(timeout=8000)
            return "已点击（选择器）：%s" % target
        except Exception:
            errors.append("选择器没点到")
    # 策略 2：可见文本
    try:
        page.get_by_text(target, exact=False).first.click(timeout=8000)
        return "已点击（文本）：%s" % target
    except Exception:
        errors.append("文本没匹配到")
    # 策略 3：按钮/链接角色
    for role in ("button", "link", "menuitem"):
        try:
            page.get_by_role(role, name=target).first.click(timeout=4000)
            return "已点击（%s 角色）：%s" % (role, target)
        except Exception:
            pass
    errors.append("角色也没找到")
    return ("点不到「%s」（%s）。建议先调 browser_get_elements 看看页面上到底有哪些可点元素，"
            "或用 view_screen 看一眼画面再决定坐标。" % (target, "、".join(errors)))


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
