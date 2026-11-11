# -*- coding: utf-8 -*-
"""core/sessionstore.py —— 网页版多会话存储

每个会话存一个 json（data/sessions/<id>.json），索引存 data/sessions_index.json。
标题自动取第一句用户消息，方便辨认。
"""
import datetime
import json
import os
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESS_DIR = os.path.join(BASE_DIR, "data", "sessions")
INDEX_PATH = os.path.join(BASE_DIR, "data", "sessions_index.json")


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _path(sid):
    return os.path.join(SESS_DIR, sid + ".json")


def list_sessions():
    """会话索引（按更新时间倒序）。"""
    idx = _load(INDEX_PATH, [])
    return sorted(idx, key=lambda x: x.get("updated", ""), reverse=True)


def create_session(title="新对话"):
    sid = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    rec = {"id": sid, "title": title, "created": _now(), "updated": _now(), "count": 0}
    idx = _load(INDEX_PATH, [])
    idx.append(rec)
    _save(INDEX_PATH, idx)
    _save(_path(sid), [])
    return rec


def load_session(sid):
    return _load(_path(sid), [])


def save_session(sid, history):
    """保存会话内容，顺手更新标题（取第一条用户消息）和更新时间。"""
    _save(_path(sid), history)
    idx = _load(INDEX_PATH, [])
    for rec in idx:
        if rec["id"] == sid:
            rec["updated"] = _now()
            rec["count"] = len(history)
            if rec.get("title") in ("", "新对话"):
                for m in history:
                    if m.get("role") == "user":
                        t = (m.get("content") or "").strip().replace("\n", " ")
                        if t:
                            rec["title"] = t[:24]
                        break
            break
    _save(INDEX_PATH, idx)


def delete_session(sid):
    try:
        os.remove(_path(sid))
    except Exception:
        pass
    idx = [r for r in _load(INDEX_PATH, []) if r["id"] != sid]
    _save(INDEX_PATH, idx)


def rename_session(sid, title):
    idx = _load(INDEX_PATH, [])
    for rec in idx:
        if rec["id"] == sid:
            rec["title"] = title[:40]
            break
    _save(INDEX_PATH, idx)


def ensure_default():
    """一个会话都没有时建一个，避免空列表。"""
    if not list_sessions():
        return create_session()
    return list_sessions()[0]
