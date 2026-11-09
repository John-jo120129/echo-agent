# -*- coding: utf-8 -*-
"""core/llm.py —— 大脑接口
所有对话大模型的地方都在这。用 OpenAI 兼容格式，换模型只改 config.json。
"""
import json
import urllib.request
import urllib.error


def call_llm(cfg, messages, tools):
    """发消息给大脑，返回它的回复（可能带 tool_calls 表示它想动手）。"""
    url = cfg["api_base"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "tools": tools,
        "stream": False
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg.get("api_key", "")
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]


def embed(texts, model="mxbai-embed-large"):
    """把文字变成向量（用于知识库检索）。跑在本机 Ollama 上。
    分批调用 + 重试，模型冷加载慢也不怕。"""
    import time
    all_vecs = []
    for i in range(0, len(texts), 16):
        batch = texts[i:i + 16]
        vecs = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    "http://localhost:11434/api/embed",
                    data=json.dumps({"model": model, "input": batch}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                vecs = data.get("embeddings")
                break
            except Exception as e:
                if attempt == 2:
                    print("  [向量化工具第%d批失败: %s]" % (i // 16 + 1, e))
                else:
                    time.sleep(3)
        if not vecs:
            return None
        all_vecs.extend(vecs)
    return all_vecs
