# -*- coding: utf-8 -*-
"""core/rag.py —— 知识库检索（RAG）
这就是"用知识库训练"的正确姿势：
  1. 把 kb/ 里的 .md 知识文件切块、变成向量，存成索引
  2. 提问时把问题也变成向量，找出最相关的几段
  3. agent 拿着这几段知识去回答——它没见过的知识也能答

索引存在 data/kb_index.json。改了 kb/ 里的文件后运行 /reindex 重建。
"""
import json
import math
import os

from core import llm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, "data", "kb_index.json")

CHUNK_SIZE = 500  # 每块大约 500 字


def _chunks_of(text):
    """按空行切块，太长的再按句号切。"""
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    result = []
    for p in parts:
        if len(p) <= CHUNK_SIZE:
            result.append(p)
        else:
            buf = ""
            for sent in p.replace("。", "。\n").split("\n"):
                if len(buf) + len(sent) > CHUNK_SIZE and buf:
                    result.append(buf)
                    buf = sent
                else:
                    buf += sent
            if buf:
                result.append(buf)
    return result


def build_index(kb_dirs):
    """扫描所有知识库文件夹，重建向量索引。返回统计。"""
    items = []
    for d in kb_dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if not fn.endswith((".md", ".txt")):
                    continue
                path = os.path.join(root, fn)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                except Exception:
                    continue
                for i, chunk in enumerate(_chunks_of(text)):
                    items.append({"file": fn, "chunk": chunk})
    if not items:
        return "知识库里没有 .md/.txt 文件，索引为空"
    print("  正在向量化 %d 个知识块……" % len(items))
    vectors = llm.embed([it["chunk"] for it in items])
    if not vectors:
        return "向量化失败：请确认 Ollama 在运行"
    for it, v in zip(items, vectors):
        it["vec"] = v
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    return "索引完成：%d 个知识块，来自 %d 个文件" % (
        len(items), len({it["file"] for it in items}))


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0
    return dot / (na * nb)


def search(query, top=5):
    """检索与问题最相关的知识块，返回给 agent 当参考。
    命中一块时，把同文件的相邻块也带上——避免只命中标题块而漏掉正文。"""
    if not os.path.exists(INDEX_PATH):
        return "知识库还没建索引，请先运行 /reindex"
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not items:
        return "知识库是空的"
    qv = llm.embed([query])
    if not qv:
        return "检索失败：请确认 Ollama 在运行"
    scored = sorted(enumerate(items),
                    key=lambda p: -_cosine(qv[0], p[1]["vec"]))[:top]
    out = []
    used = set()
    for idx, it in scored:
        if idx in used:
            continue
        used.add(idx)
        seg = it["chunk"]
        for di in (-1, 1):   # 带上同文件的前后相邻块
            j = idx + di
            if 0 <= j < len(items) and items[j]["file"] == it["file"] and j not in used:
                used.add(j)
                seg += "\n\n" + items[j]["chunk"]
        out.append("【来自 %s】%s" % (it["file"], seg))
    return "\n---\n".join(out)
