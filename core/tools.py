# -*- coding: utf-8 -*-
"""core/tools.py —— agent 的双手（工具集）

这就是"真 agent"和"聊天助手"的区别：这些工具能真碰你的电脑。
模型不会直接执行任何东西——它只能"点菜"（返回工具名+参数），
由 run_tool() 替它执行，结果再喂回去给它看。

安全设计：
  - 危险命令（删除/格式化/关机等）执行前必须你按 y 确认
  - 往 workspace/ 和项目目录以外写文件也要确认
  - 命令超时 90 秒自动掐断
"""
import os
import re
import ssl
import subprocess
import urllib.parse
import urllib.request
import html as html_mod

from core import memory
from core import rag
from core import skills
from core import computer
from core import browser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------- 安全 ----------
DANGEROUS = re.compile(
    r"(^|\s|[/|&;])(rm|del|rd|rmdir|format|shutdown|diskpart|cipher|"
    r"reg\s+(delete|add)|remove-item|clear-content|mkfs)\b", re.I)

WORKSPACE = os.path.join(BASE_DIR, "workspace")


def _ask_confirm(prompt):
    """向用户要一个 y/n。echo.py 会把它换成真交互。"""
    return ctx["confirm_fn"](prompt)


# 工具执行时需要的上下文（auto 模式开关、确认函数），由 echo.py 注入
ctx = {"auto": False, "confirm_fn": lambda p: False}


# ---------- 工具实现 ----------
def _trim(text, limit=6000):
    text = text if isinstance(text, str) else str(text)
    if len(text) > limit:
        return text[:limit] + "\n……（太长已截断）"
    return text


def t_read_file(args):
    path = os.path.abspath(args["path"])
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return _trim(f.read(), 8000)
    except Exception as e:
        return "读不了：%s" % e


def t_write_file(args):
    path = os.path.abspath(args["path"])
    safe = path.startswith(BASE_DIR) or path.startswith(WORKSPACE)
    if not safe and not ctx["auto"]:
        if not _ask_confirm("往项目/workspace 以外写文件：%s" % path):
            return "用户拒绝了，未写入"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(args["content"])
    return "已写入 %s（%d 字）" % (path, len(args["content"]))


def t_list_dir(args):
    path = os.path.abspath(args.get("path", "."))
    if not os.path.isdir(path):
        return "不是文件夹：%s" % path
    out = []
    for root, dirs, files in os.walk(path):
        depth = root[len(path):].count(os.sep)
        if depth >= 2:                      # 只看两层，防止刷屏
            dirs[:] = []
            continue
        for name in dirs + files:
            out.append(os.path.join(root, name))
        if len(out) > 200:
            break
    return _trim("\n".join(out) or "（空文件夹）")


def t_search_files(args):
    keyword = args["keyword"]
    path = os.path.abspath(args.get("path", WORKSPACE))
    hits = []
    for root, dirs, files in os.walk(path):
        if root[len(path):].count(os.sep) >= 4:
            dirs[:] = []
            continue
        for name in files:
            if keyword.lower() in name.lower():
                hits.append(os.path.join(root, name))
                if len(hits) >= 50:
                    return _trim("\n".join(hits))
    return _trim("\n".join(hits) or "没找到含「%s」的文件" % keyword)


def t_run_command(args):
    cmd = args["command"]
    if DANGEROUS.search(cmd) and not ctx["auto"]:
        if not _ask_confirm("要执行危险命令：%s" % cmd):
            return "用户拒绝了这条命令"
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, timeout=90,
            cwd=WORKSPACE if os.path.isdir(WORKSPACE) else None)
        out = ""
        for b in (r.stdout, r.stderr):
            if not b:
                continue
            try:
                out += b.decode("utf-8") + "\n"
            except UnicodeDecodeError:
                out += b.decode("gbk", errors="replace") + "\n"
        return _trim("退出码 %d\n%s" % (r.returncode, out.strip() or "（无输出）"))
    except subprocess.TimeoutExpired:
        return "命令超过 90 秒没跑完，已被掐断"
    except Exception as e:
        return "执行失败：%s" % e


def t_web_fetch(args):
    url = args["url"]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EchoAgent"})
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return "抓取失败：%s" % e
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return _trim(text, 6000) or "（页面没抓到文字）"


def t_web_search(args):
    """联网搜索全网公开知识（必应），返回标题+链接+摘要。"""
    query = args["query"]
    url = ("https://cn.bing.com/search?q=" + urllib.parse.quote(query) +
           "&count=10&setlang=zh-CN")
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0 Safari/537.36")})
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return "搜索失败：%s" % e
    out = []
    for m in re.finditer(r'<li class="b_algo".*?</li>', raw, re.S):
        block = m.group(0)
        tm = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not tm:
            continue
        title = html_mod.unescape(re.sub(r"<[^>]+>", "", tm.group(2))).strip()
        link = tm.group(1)
        sm = re.search(r'<p[^>]*class="[^"]*b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.S)
        snip = html_mod.unescape(re.sub(r"<[^>]+>", "", sm.group(1))).strip() if sm else ""
        if title and link:
            out.append("%s\n  链接：%s\n  摘要：%s" % (title, link, snip))
        if len(out) >= 5:
            break
    return _trim("\n\n".join(out), 4000) or "没搜到结果，换个关键词试试"


def t_search_kb(args):
    return rag.search(args["query"])


def t_set_reminder(args):
    return memory.set_reminder(float(args["minutes"]), args["text"])


# ---------- 工具清单（给模型看的"菜单"） ----------
TOOLS = [
    {"type": "function", "function": {
        "name": "run_command",
        "description": "在这台电脑上执行一条命令行命令（Windows cmd）。适合：跑python、安装东西、查看系统信息、git操作等。危险命令会被要求用户确认。",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string", "description": "完整命令，比如 python xx.py 或 dir"}},
                       "required": ["command"]}
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取一个本地文本文件的内容",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string", "description": "文件绝对路径或相对路径"}},
                       "required": ["path"]}
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "把内容写入本地文件（新建或覆盖）。写代码、写文档、保存结果都用它。",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string", "description": "目标路径"},
                                      "content": {"type": "string", "description": "完整文件内容"}},
                       "required": ["path", "content"]}
    }},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "列出文件夹里的内容（含子文件夹，最多两层）",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string", "description": "文件夹路径，默认项目目录"}}
                       }
    }},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "按文件名关键词搜索本地文件",
        "parameters": {"type": "object",
                       "properties": {"keyword": {"type": "string", "description": "文件名关键词"},
                                      "path": {"type": "string", "description": "从哪个文件夹开始搜，默认 workspace"}},
                       "required": ["keyword"]}
    }},
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "抓取一个网页的正文文字（只读）。需要查网上资料时用。",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string", "description": "网址"}},
                       "required": ["url"]}
    }},
    {"type": "function", "function": {
        "name": "search_kb",
        "description": "检索本地知识库（kb/ 文件夹），返回最相关的几段知识。用户的问题涉及知识库内容时先查这里。",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "检索问题"}},
                       "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "联网搜索全网公开知识（必应）。本地知识库 search_kb 查不到、或需要公开/最新信息时用它。返回标题+链接+摘要。",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                       "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "remember",
        "description": "把用户的重要信息写入短期记忆，重启不丢。用户说'记住'时必须用。",
        "parameters": {"type": "object",
                       "properties": {"content": {"type": "string", "description": "一句话概括要记的内容"}},
                       "required": ["content"]}
    }},
    {"type": "function", "function": {
        "name": "remember_long",
        "description": "把重要、长期有效的信息（人生目标、长期约定、重大事件）存入长期记忆。用户说'记住我的长期目标/长期计划'时调用。",
        "parameters": {"type": "object",
                       "properties": {"content": {"type": "string", "description": "要长期记住的内容"}},
                       "required": ["content"]}
    }},
    {"type": "function", "function": {
        "name": "remember_profile",
        "description": "把用户的稳定个人信息存入档案。姓名、年龄、身份、城市、职业、学校等。key 是字段名（如'姓名'），value 是值（如'溯游'）。用户说'我叫X/我今年X岁/我是X'时调用。",
        "parameters": {"type": "object",
                       "properties": {"key": {"type": "string", "description": "字段名，如 姓名/年龄/身份/城市"},
                                      "value": {"type": "string", "description": "值，如 溯游/14/初中生"}},
                       "required": ["key", "value"]}
    }},
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "列出当前可用的技能（Skill）清单。做专业任务（如设计网页）前先看有哪些技能。",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "use_skill",
        "description": "加载某个技能的完整规范/工作手册，照着它执行任务。",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string", "description": "技能名，先 list_skills 查看"}},
                       "required": ["name"]}
    }},
    {"type": "function", "function": {
        "name": "add_todo",
        "description": "给用户添加待办事项",
        "parameters": {"type": "object",
                       "properties": {"task": {"type": "string"}},
                       "required": ["task"]}
    }},
    {"type": "function", "function": {
        "name": "write_diary",
        "description": "帮用户写日记",
        "parameters": {"type": "object",
                       "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["title", "content"]}
    }},
    {"type": "function", "function": {
        "name": "get_time",
        "description": "获取当前时间",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "set_reminder",
        "description": "设一个提醒，到时间会主动告诉用户（agent 保持运行时有效）",
        "parameters": {"type": "object",
                       "properties": {"minutes": {"type": "number", "description": "几分钟后提醒"},
                                      "text": {"type": "string", "description": "提醒内容"}},
                       "required": ["minutes", "text"]}
    }},
    {"type": "function", "function": {
        "name": "screenshot",
        "description": "对当前屏幕截图并保存到文件。需要看清屏幕现状时用。",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "read_screen",
        "description": "读取当前屏幕上能识别的所有文字（Windows 自带 OCR）。操控电脑前先用它了解屏幕上有哪些内容。",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "read_controls",
        "description": "读当前窗口的控件（文字+坐标），可据此精准点击。对桌面软件很准，对网页/浏览器应用可能读不到。",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "view_screen",
        "description": "截屏并发给多模态模型真正'看懂'屏幕画面（文字、图标、窗口、布局）。需要判断屏幕上有什么、长什么样时用它。",
        "parameters": {"type": "object",
                       "properties": {"prompt": {"type": "string", "description": "想让模型重点看什么（可选）"}}}
    }},
    {"type": "function", "function": {
        "name": "mouse_move",
        "description": "把鼠标移动到屏幕上的某个坐标。",
        "parameters": {"type": "object",
                       "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                       "required": ["x", "y"]}
    }},
    {"type": "function", "function": {
        "name": "mouse_click",
        "description": "点击鼠标。给 x/y 就点那个位置，不给就点当前位置。button 可选 left/right/middle。",
        "parameters": {"type": "object",
                       "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                      "button": {"type": "string"}}}
    }},
    {"type": "function", "function": {
        "name": "mouse_scroll",
        "description": "滚动鼠标滚轮。amount 正数向上滚，负数向下滚。",
        "parameters": {"type": "object",
                       "properties": {"amount": {"type": "integer"}},
                       "required": ["amount"]}
    }},
    {"type": "function", "function": {
        "name": "type_text",
        "description": "在当前位置输入文字（支持中文，中文走剪贴板粘贴）。enter 为 true 时输入后回车。",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string", "description": "要输入的文字"},
                                      "enter": {"type": "boolean", "description": "是否回车"}},
                       "required": ["text"]}
    }},
    {"type": "function", "function": {
        "name": "press_key",
        "description": "按一个键，如 enter / tab / esc / f5 / 方向键等。",
        "parameters": {"type": "object",
                       "properties": {"key": {"type": "string", "description": "键名"}},
                       "required": ["key"]}
    }},
    {"type": "function", "function": {
        "name": "browser_open",
        "description": "打开一个网页。之后的浏览器操作都针对这个页面。",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string", "description": "网址"}},
                       "required": ["url"]}
    }},
    {"type": "function", "function": {
        "name": "browser_read",
        "description": "读取当前浏览器页面的文字内容。",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "browser_click",
        "description": "点击网页上的元素。target 可以是可见文字（如'登录'）或 CSS 选择器（如'#submit'）。",
        "parameters": {"type": "object",
                       "properties": {"target": {"type": "string", "description": "要点的文字或选择器"}},
                       "required": ["target"]}
    }},
    {"type": "function", "function": {
        "name": "browser_type",
        "description": "在网页输入框里填文字。selector 是输入框的 CSS 选择器。",
        "parameters": {"type": "object",
                       "properties": {"selector": {"type": "string", "description": "输入框选择器，如 input[name=q]"},
                                      "text": {"type": "string", "description": "要填的内容"}},
                       "required": ["selector", "text"]}
    }},
    {"type": "function", "function": {
        "name": "browser_screenshot",
        "description": "截当前浏览器页面。",
        "parameters": {"type": "object", "properties": {}}
    }},
]

_IMPL = {
    "run_command": t_run_command,
    "read_file": t_read_file,
    "write_file": t_write_file,
    "list_dir": t_list_dir,
    "search_files": t_search_files,
    "web_fetch": t_web_fetch,
    "search_kb": t_search_kb,
    "web_search": t_web_search,
    "remember": lambda a: memory.add_fact(a.get("content", "")),
    "remember_long": lambda a: memory.add_long_term(a.get("content", "")),
    "remember_profile": lambda a: memory.set_profile(a.get("key", ""), a.get("value", "")),
    "list_skills": lambda a: "\n".join(
        "- %s：%s（%s）" % (s["name"], s["description"], s["when"])
        for s in skills.list_skills()) or "还没有安装任何技能",
    "use_skill": lambda a: skills.load_skill(a.get("name", "")),
    "add_todo": lambda a: memory.add_todo(a.get("task", "")),
    "write_diary": lambda a: memory.write_diary(a.get("title", ""), a.get("content", "")),
    "get_time": lambda a: memory.now_str(),
    "set_reminder": t_set_reminder,
    "screenshot": lambda a: computer.screenshot(),
    "read_screen": lambda a: computer.read_screen(),
    "read_controls": lambda a: computer.read_controls(),
    "view_screen": lambda a: computer.view_screen(ctx.get("cfg", {}), a.get("prompt")),
    "mouse_move": lambda a: computer.mouse_move(a.get("x", 0), a.get("y", 0)),
    "mouse_click": lambda a: computer.mouse_click(a.get("x"), a.get("y"), a.get("button", "left")),
    "mouse_scroll": lambda a: computer.mouse_scroll(a.get("amount", 0)),
    "type_text": lambda a: computer.type_text(a.get("text", ""), bool(a.get("enter", False))),
    "press_key": lambda a: computer.press_key(a.get("key", "")),
    "browser_open": lambda a: browser.browser_open(a.get("url", "")),
    "browser_read": lambda a: browser.browser_read(),
    "browser_click": lambda a: browser.browser_click(a.get("target", "")),
    "browser_type": lambda a: browser.browser_type(a.get("selector", ""), a.get("text", "")),
    "browser_screenshot": lambda a: browser.browser_screenshot(),
}


def run_tool(name, args):
    try:
        fn = _IMPL.get(name)
        if not fn:
            return "未知工具：%s" % name
        return fn(args)
    except Exception as e:
        return "工具出错：%s" % e
