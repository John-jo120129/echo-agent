# -*- coding: utf-8 -*-
"""core/memory.py —— 记忆系统（四层 + 记忆养成）

记忆分四层，全部存在 data/ 文件夹，关机不丢：
  working   → history.json   当前/最近对话（工作记忆）
  short     → facts.json     短期事实记忆（"我喜欢喝可乐"）
  long      → long_term.json 长期重要记忆（自动总结归档）
  user      → user_profile.json  用户档案（身份、偏好，最高优先级）

记忆养成（无限上下文）：
  每次会话退出时，把本次对话自动总结成记忆，追加写进
  data/memories/YYYY-MM-DD.md；越攒越多 = "越肥"。
  这些记忆文件纳入知识库索引，对话时按相关性检索注入，
  从而突破大模型的上下文长度限制，实现"无限上下文"。
"""
import json
import os
import datetime
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FACTS_PATH = os.path.join(DATA_DIR, "facts.json")
TODO_PATH = os.path.join(DATA_DIR, "todo.json")
DIARY_DIR = os.path.join(DATA_DIR, "diary")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
LONG_TERM_PATH = os.path.join(DATA_DIR, "long_term.json")
PROFILE_PATH = os.path.join(DATA_DIR, "user_profile.json")
MEMORIES_DIR = os.path.join(DATA_DIR, "memories")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")

# 会话内提醒（存内存，退出即消失）
_reminders = []
_reminder_lock = threading.Lock()


def _load(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _similar(a, b):
    """简单字符集合重叠度，用于记忆去重。返回 0~1。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def today_str():
    return datetime.date.today().strftime("%Y-%m-%d")


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_facts():
    return _load(FACTS_PATH, [])


def add_fact(text):
    facts = load_facts()
    for f in facts:
        if _similar(text, f["text"]) > 0.72 or f["text"] in text or text in f["text"]:
            return "这条已经记过了：%s" % f["text"]
    facts.append({"date": today_str(), "text": text})
    _save(FACTS_PATH, facts)
    return "已记住，现有 %d 条记忆" % len(facts)


def load_todos():
    return _load(TODO_PATH, [])


def add_todo(task):
    todos = load_todos()
    todos.append({"id": len(todos) + 1, "task": task, "done": False, "date": today_str()})
    _save(TODO_PATH, todos)
    return "待办已添加（编号 %d）" % len(todos)


def finish_todo(num):
    todos = load_todos()
    for t in todos:
        if t["id"] == num:
            t["done"] = True
            _save(TODO_PATH, todos)
            return "待办 [%d] %s 已完成" % (num, t["task"])
    return "没找到编号 %d 的待办" % num


def write_diary(title, content):
    os.makedirs(DIARY_DIR, exist_ok=True)
    path = os.path.join(DIARY_DIR, "%s.md" % today_str())
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n## %s（%s）\n%s\n" % (title, now_str(), content))
    return "日记已写入 %s" % os.path.basename(path)


def load_history(limit=30):
    return _load(HISTORY_PATH, [])[-limit:]


def save_history(history, limit=200):
    _save(HISTORY_PATH, history[-limit:])


def set_reminder(minutes, text):
    at = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    with _reminder_lock:
        _reminders.append({"at": at, "text": text})
    return "提醒已设定：%s 时提醒你「%s」" % (at.strftime("%H:%M"), text)


def check_reminders():
    """返回到点的提醒列表（主循环每次输入前后调用）。"""
    due = []
    now = datetime.datetime.now()
    with _reminder_lock:
        for r in _reminders[:]:
            if r["at"] <= now:
                due.append(r["text"])
                _reminders.remove(r)
    return due


# ---------- 用户档案（最高优先级） ----------
def load_profile():
    return _load(PROFILE_PATH, {})


def set_profile(key, value):
    p = load_profile()
    p[key] = value
    _save(PROFILE_PATH, p)
    return "已记住你的「%s」" % key


def remove_profile(key):
    p = load_profile()
    if key in p:
        del p[key]
        _save(PROFILE_PATH, p)
        return "已忘记你的「%s」" % key
    return "档案里没有「%s」" % key


# ---------- 长期记忆 ----------
def load_long_term():
    return _load(LONG_TERM_PATH, [])


def add_long_term(text, kind="memory"):
    items = load_long_term()
    for it in items:
        if _similar(text, it["text"]) > 0.72 or it["text"] in text or text in it["text"]:
            return "这条长期记忆已经存在：%s" % it["text"]
    items.append({"date": today_str(), "kind": kind, "text": text})
    _save(LONG_TERM_PATH, items)
    return "已存入长期记忆（共 %d 条）" % len(items)


# ---------- 记忆养成：会话归档为记忆文件 ----------
def write_memory_md(title, text):
    """把一条记忆追加写进 data/memories/YYYY-MM-DD.md（供检索，实现无限上下文）。"""
    os.makedirs(MEMORIES_DIR, exist_ok=True)
    path = os.path.join(MEMORIES_DIR, "%s.md" % today_str())
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n## %s（%s）\n%s\n" % (title, now_str(), text))
    return path


def collect_all_memories():
    """汇总所有记忆，供 3D 记忆星球展示用。"""
    result = {"profile": [], "facts": [], "long_term": [], "memories": []}
    for k, v in load_profile().items():
        result["profile"].append({"k": k, "v": v})
    for f in load_facts():
        result["facts"].append(f)
    for l in load_long_term():
        result["long_term"].append(l)
    if os.path.isdir(MEMORIES_DIR):
        for fn in sorted(os.listdir(MEMORIES_DIR)):
            if fn.endswith(".md"):
                with open(os.path.join(MEMORIES_DIR, fn), "r", encoding="utf-8") as f:
                    result["memories"].append({"file": fn, "text": f.read()[:600]})
    return result


def search_memory(query, top=8):
    """检索全部记忆（短期+长期+归档），返回相关的记忆条目。"""
    def match(text):
        return _similar(query, text) > 0.22 or any(w in text for w in query if len(w) >= 2)

    hits = []
    for f in load_facts():
        if match(f["text"]):
            hits.append(("短期", f["text"]))
    for l in load_long_term():
        if match(l["text"]):
            hits.append(("长期", l["text"]))
    if os.path.isdir(MEMORIES_DIR):
        for fn in sorted(os.listdir(MEMORIES_DIR)):
            if not fn.endswith(".md"):
                continue
            try:
                with open(os.path.join(MEMORIES_DIR, fn), "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            for line in content.splitlines():
                line = line.strip().lstrip("#-·* ")
                if line and match(line):
                    hits.append(("归档(%s)" % fn[:10], line))
    if not hits:
        return "没找到相关记忆"
    return "\n".join("- [%s] %s" % (k, v) for k, v in hits[:top])


# ---------- 定时任务 ----------
def load_schedule():
    return _load(SCHEDULE_PATH, [])


def save_schedule(items):
    _save(SCHEDULE_PATH, items)


def add_schedule(time_str, task):
    s = load_schedule()
    s.append({"time": time_str, "task": task, "last_run": ""})
    save_schedule(s)
    return "已添加定时任务：每天 %s 执行「%s」" % (time_str, task)


def list_schedule():
    s = load_schedule()
    if not s:
        return "还没有定时任务。用法：/schedule 08:00 任务内容"
    return "\n".join("- 每天 %s：%s" % (x["time"], x["task"]) for x in s)
