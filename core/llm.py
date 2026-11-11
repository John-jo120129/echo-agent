# -*- coding: utf-8 -*-
"""core/llm.py —— 大脑接口
所有对话大模型的地方都在这。用 OpenAI 兼容格式，换模型只改 config.json。
"""
import json
import urllib.request
import urllib.error


def call_llm(cfg, messages, tools, on_token=None, temperature=None):
    """发消息给大脑，返回它的回复（可能带 tool_calls 表示它想动手）。
    传 on_token 回调则走流式：边生成边逐段回调（体验上不用干等）。
    temperature 不给就用 cfg 里的（默认 0.7）；工具调用建议传 0.2，减少格式漂移。"""
    url = cfg["api_base"].rstrip("/") + "/chat/completions"
    temp = temperature if temperature is not None else cfg.get("temperature", 0.7)
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "tools": tools,
        "temperature": temp,
        "stream": bool(on_token)
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
    if on_token:
        # 流式：逐段读 SSE，拼 content 和 tool_calls
        content = ""
        tc_map = {}
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except Exception:
                    continue
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        content += delta["content"]
                        on_token(delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        i = tc.get("index", 0)
                        e = tc_map.setdefault(i, {"id": "", "name": "", "args": ""})
                        if tc.get("id"):
                            e["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            e["name"] = fn["name"]
                        if fn.get("arguments"):
                            e["args"] += fn["arguments"]
        tool_calls = [{"id": tc_map[i]["id"], "type": "function",
                       "function": {"name": tc_map[i]["name"],
                                    "arguments": tc_map[i]["args"]}}
                      for i in sorted(tc_map)] or None
        return {"content": content, "tool_calls": tool_calls}

    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]


def call_vision(cfg, prompt, image_paths):
    """把图片发给多模态模型看图理解。用 cfg 里的 vision_model。
    注意：走 /v1/chat/completions 时图片用 OpenAI 的 image_url 格式。"""
    import base64
    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + b64}})
    model = cfg.get("vision_model", "qwen2.5vl:7b")
    url = cfg["api_base"].rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "options": {"num_ctx": 8192},   # 多帧图片需要更大的上下文窗口
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
    return data["choices"][0]["message"].get("content", "")


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
