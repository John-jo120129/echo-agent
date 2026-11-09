# -*- coding: utf-8 -*-
"""core/memory.py —— 记忆系统
agent 的长期记忆全部存在 data/ 文件夹，关机不丢：
  facts.json    长期事实记忆（"用户喜欢喝可乐"）
  todo.json     待办清单
  diary/        日记
  history.json  跨会话对话历史（最近 30 条自动续上）
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


def today_str():
    return datetime.date.today().strftime("%Y-%m-%d")


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_facts():
    return _load(FACTS_PATH, [])


def add_fact(text):
    facts = load_facts()
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
