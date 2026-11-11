# -*- coding: utf-8 -*-
"""core/computer.py —— 电脑操控（屏幕 + 鼠标 + 键盘）

这就是"Computer Use"的双手：
  screenshot   截屏
  read_screen  读屏幕上的文字（Windows 自带 OCR）
  mouse_move / mouse_click / mouse_double / mouse_drag / mouse_scroll
  type_text / press_key / hotkey

注意：
  - 真鼠标只有一个，动了就看得见（物理限制）；"隐藏"靠 stealth 模式静默+瞬移
  - 中文输入走剪贴板粘贴（pyautogui 只能打 ASCII）
  - 屏幕尺寸/坐标：读屏拿到的文字暂不带坐标（Windows OCR 限制），
    精准点击坐标需要 tesseract 引擎（见 read_screen 的说明）
"""
import json
import os
import subprocess

import pyautogui

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_PS1 = os.path.join(BASE_DIR, "core", "ocr.ps1")
SCREEN_TMP = os.path.join(BASE_DIR, "data", "_screen.png")

# 隐藏模式（静默 + 瞬移），由 echo.py 注入
ctx = {"stealth": False}

pyautogui.FAILSAFE = True   # 鼠标甩到左上角可紧急中止
pyautogui.PAUSE = 0.0


def _dur():
    """隐藏模式瞬移，可视化模式平滑移动。"""
    return 0.0 if ctx["stealth"] else 0.3


def screenshot(path=None):
    path = path or SCREEN_TMP
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pyautogui.screenshot().save(path)
    return "已截屏保存到 %s（尺寸 %s）" % (path, pyautogui.size())


def read_screen():
    """截屏并用 Windows OCR 读屏幕文字。返回识别到的文字（不含坐标）。"""
    os.makedirs(os.path.dirname(SCREEN_TMP), exist_ok=True)
    pyautogui.screenshot().save(SCREEN_TMP)
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", OCR_PS1, SCREEN_TMP],
            capture_output=True, timeout=60)
        out = r.stdout
        for enc in ("utf-8", "gbk"):
            try:
                text = out.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = ""
        items = json.loads(text.strip() or "[]")
    except Exception:
        items = []
    if not items:
        return "（屏幕没识别到文字）"
    texts = [it["text"].replace(" ", "") for it in items if it.get("text")]
    return "屏幕上的文字（按识别顺序）：\n" + "\n".join("- " + t for t in texts)


def mouse_move(x, y):
    pyautogui.moveTo(int(x), int(y), duration=_dur())
    return "鼠标已移动到 (%d, %d)" % (int(x), int(y))


def mouse_click(x=None, y=None, button="left"):
    if x is not None and y is not None:
        pyautogui.click(int(x), int(y), button=button)
        return "已点击 (%d, %d) %s键" % (int(x), int(y), button)
    pyautogui.click(button=button)
    return "已在当前位置点击 %s 键" % button


def find_control(target):
    """按文字找控件/桌面图标的屏幕坐标。优先找桌面图标，再找其他窗口。"""
    try:
        import uiautomation as auto
        auto.SetGlobalSearchTimeout(2)
        root = auto.GetRootControl()

        def search_tree(ctrl, depth, max_depth=10):
            if depth > max_depth:
                return None
            try:
                for c in ctrl.GetChildren():
                    try:
                        name = c.Name or ""
                        if name and target.lower() in name.lower():
                            r = c.BoundingRectangle
                            if r.width() > 0 and r.height() > 0:
                                return (int((r.left + r.right) // 2),
                                        int((r.top + r.bottom) // 2))
                    except Exception:
                        pass
                    res = search_tree(c, depth + 1, max_depth)
                    if res:
                        return res
            except Exception:
                pass
            return None

        # 1. 优先找桌面（Progman / WorkerW / Program Manager）里的图标
        for win in root.GetChildren():
            try:
                cn = win.ClassName or ""
                nm = win.Name or ""
                if cn in ("Progman", "WorkerW") or "Program Manager" in nm:
                    pt = search_tree(win, 0)
                    if pt:
                        return pt
            except Exception:
                pass

        # 2. 再找其他窗口
        for win in root.GetChildren():
            pt = search_tree(win, 0)
            if pt:
                return pt
        return None
    except Exception:
        return None


def mouse_double(x=None, y=None, target=None):
    if target:
        pt = find_control(target)
        if not pt:
            return "没找到叫「%s」的图标/控件，先用 read_controls 或 view_screen 看看它在哪" % target
        x, y = pt
    if x is not None and y is not None:
        pyautogui.moveTo(int(x), int(y), duration=0.2)
        pyautogui.doubleClick(int(x), int(y))
        return "已移动并双击 (%d, %d)" % (int(x), int(y))
    return "缺少坐标：请给 x/y，或给 target（要找的图标/按钮文字）"


def mouse_drag(x1, y1, x2, y2):
    pyautogui.moveTo(int(x1), int(y1), duration=_dur())
    pyautogui.dragTo(int(x2), int(y2), duration=0.5)
    return "已从 (%d,%d) 拖到 (%d,%d)" % (int(x1), int(y1), int(x2), int(y2))


def mouse_scroll(amount):
    pyautogui.scroll(int(amount))
    return "已滚动 %d 格" % int(amount)


def type_text(text, enter=False):
    has_cn = any(ord(c) > 127 for c in text)
    if has_cn:
        # 中文走剪贴板粘贴
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Set-Clipboard -Value ([System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')))"
                 % _b64(text)], timeout=10)
            pyautogui.hotkey("ctrl", "v")
        except Exception as e:
            return "中文输入失败：%s" % e
    else:
        pyautogui.write(text, interval=0.01 if ctx["stealth"] else 0.03)
    if enter:
        pyautogui.press("enter")
    return "已输入：%s" % text


def press_key(key):
    pyautogui.press(key)
    return "已按下按键 " + key


def hotkey(*keys):
    pyautogui.hotkey(*keys)
    return "已按快捷键 " + "+".join(keys)


def read_controls(max_items=40):
    """用 Windows UI Automation 读当前窗口的控件（文字 + 坐标）。
    对原生 Windows 软件（资源管理器、记事本、对话框等）很准；
    对网页/浏览器应用（Chromium）控件树默认是空的，那种场景建议走网页自动化。"""
    try:
        import uiautomation as auto
        auto.SetGlobalSearchTimeout(2)
        w = auto.GetForegroundControl()
        items = []

        def walk(ctrl, depth):
            if depth > 4 or len(items) >= max_items:
                return
            for c in ctrl.GetChildren():
                try:
                    name = c.Name
                    if name and name.strip():
                        r = c.BoundingRectangle
                        items.append({"text": name.strip()[:40],
                                      "x": r.left, "y": r.top,
                                      "w": r.width(), "h": r.height()})
                    walk(c, depth + 1)
                except Exception:
                    continue

        walk(w, 0)
        if not items:
            return ("当前窗口「%s」没读到控件（可能是网页/浏览器应用，"
                    "这种建议直接说清楚要操作哪个网页元素）" % w.Name)
        lines = ["- %s @(%d,%d)" % (it["text"], it["x"], it["y"]) for it in items]
        return "当前窗口「%s」的控件（文字@坐标，可据此点击）：\n%s" % (w.Name, "\n".join(lines))
    except Exception as e:
        return "读控件失败：%s" % e


def view_screen(cfg, prompt=None):
    """截屏并发给多模态模型'看图'理解画面。返回它对屏幕内容的描述。
    需要 cfg（含 vision_model）。模型没下载好时会给出友好提示。"""
    from core import llm
    prompt = prompt or ("请描述这个屏幕画面：上面有哪些窗口、按钮、图标、文字，"
                        "各自大致在什么位置。重点说清如果要操作应该点哪里。")
    os.makedirs(os.path.dirname(SCREEN_TMP), exist_ok=True)
    img = pyautogui.screenshot()
    # 缩到合适尺寸，避免超过视觉模型的输入上限
    w, h = img.size
    if max(w, h) > 1280:
        scale = 1280.0 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)))
    img.save(SCREEN_TMP)
    try:
        return llm.call_vision(cfg, prompt, [SCREEN_TMP])
    except Exception as e:
        return ("看图失败：%s。\n提示：确认多模态模型已下载（ollama pull %s）"
                % (e, cfg.get("vision_model", "qwen2.5vl:7b")))


def _b64(s):
    import base64
    return base64.b64encode(s.encode("utf-8")).decode("ascii")
