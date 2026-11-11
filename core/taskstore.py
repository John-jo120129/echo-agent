# -*- coding: utf-8 -*-
"""core/taskstore.py —— 长任务持久化

解决的问题：任务跑到一半（进程崩了 / 用户关了窗口 / 超时），
下次打开完全不知道上次干了什么。

做法：每个任务落一个 json 记录（输入、走了几步、调了哪些工具、状态），
下次启动能捡起"没做完的任务"，也能回看历史任务都干了啥。
"""
import datetime
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(BASE_DIR, "data", "tasks")


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _path(task_id):
    return os.path.join(TASKS_DIR, task_id + ".json")


def _save(task_id, record):
    try:
        os.makedirs(TASKS_DIR, exist_ok=True)
        record["updated"] = _now()
        with open(_path(task_id), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def start_task(user_input):
    """开始一个新任务，返回 task_id。"""
    task_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    record = {
        "id": task_id,
        "input": user_input[:500],
        "status": "running",
        "steps": 0,
        "calls": [],
        "started": _now(),
        "updated": _now(),
    }
    _save(task_id, record)
    return task_id


def update_task(task_id, step, call_log=None):
    """更新任务进度（每步调用一次）。"""
    if not task_id:
        return
    try:
        with open(_path(task_id), "r", encoding="utf-8") as f:
            record = json.load(f)
    except Exception:
        return
    record["steps"] = step
    if call_log is not None:
        record["calls"] = call_log[-30:]      # 只留最近 30 条
    _save(task_id, record)


def finish_task(task_id, status="done", reply=""):
    """结束任务：done / failed。"""
    if not task_id:
        return
    try:
        with open(_path(task_id), "r", encoding="utf-8") as f:
            record = json.load(f)
    except Exception:
        return
    record["status"] = status
    record["reply"] = (reply or "")[:500]
    record["finished"] = _now()
    _save(task_id, record)


def running_tasks():
    """返回所有没做完的任务（按时间倒序）。"""
    out = []
    if not os.path.isdir(TASKS_DIR):
        return out
    for fn in sorted(os.listdir(TASKS_DIR), reverse=True):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(TASKS_DIR, fn), "r", encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            continue
        if rec.get("status") == "running":
            out.append(rec)
    return out


def last_running():
    """最近一个没做完的任务，没有就返回 None。"""
    r = running_tasks()
    return r[0] if r else None


def recent_tasks(limit=10):
    """最近的任务列表（不管状态）。"""
    out = []
    if not os.path.isdir(TASKS_DIR):
        return out
    for fn in sorted(os.listdir(TASKS_DIR), reverse=True)[:limit]:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(TASKS_DIR, fn), "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out
