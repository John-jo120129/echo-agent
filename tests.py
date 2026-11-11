# -*- coding: utf-8 -*-
"""tests.py —— Echo 工具调用测试集

为什么要有它：换模型、改提示词、改代码之后，你根本不知道它是不是"变笨了"。
工具调用错误是确定性的（选错工具/参数不对一眼就能看出来），不需要模型裁判，
是最便宜、最有价值的一层评测。

用法：
    python tests.py              # 用 config.json 里的模型测
    python tests.py qwen2.5:7b   # 指定模型测
"""
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core import llm, tools   # noqa: E402

# 每条：输入 → 期望调用哪个工具（允许多个，因为有些说法本身有歧义）
CASES = [
    {"in": "打开记事本", "expect": ["open_app"]},
    {"in": "双击桌面上的 Blender 图标", "expect": ["mouse_double"]},
    {"in": "看看我的屏幕上有什么", "expect": ["read_screen", "view_screen"]},
    {"in": "把「你好」写到 D:/echo-agent/workspace/a.txt 里", "expect": ["write_file"]},
    {"in": "读一下 D:/echo-agent/config.json 的内容", "expect": ["read_file"]},
    {"in": "列一下 D:/echo-agent 目录里有什么", "expect": ["list_dir"]},
    {"in": "执行命令 ipconfig 看看本机 IP", "expect": ["run_command"]},
    {"in": "网上搜一下 Qwen 最新版本", "expect": ["web_search"]},
    {"in": "打开网页 https://www.baidu.com", "expect": ["browser_open", "web_fetch"]},
    {"in": "记住我喜欢喝可乐", "expect": ["remember", "remember_profile", "remember_long"]},
    {"in": "回想一下我之前说过什么", "expect": ["search_kb", "recall", "search_memory"]},
    {"in": "现在几点了", "expect": ["get_time"]},
    {"in": "把这句话念出来：你好", "expect": ["speak"]},
    {"in": "看看这个视频 D:/echo-agent/workspace/test.mp4", "expect": ["video_understand"]},
    {"in": "点击屏幕坐标 500, 300", "expect": ["mouse_click"]},
    {"in": "在当前位置打上 hello", "expect": ["type_text"]},
    {"in": "按一下回车键", "expect": ["press_key"]},
    {"in": "向下滚动 5 格", "expect": ["mouse_scroll"]},
    {"in": "把鼠标移到 100,100", "expect": ["mouse_move"]},
    {"in": "截一张当前网页的图", "expect": ["browser_screenshot"]},
]


def _load_cfg():
    with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _parse_text_call(text):
    """7b 有时把工具调用写成 JSON 文本，这里也兜一下。"""
    m = re.search(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}',
                  text or "", re.S)
    if m:
        return m.group(1), m.group(2)
    return None, None


def run(model=None):
    cfg = _load_cfg()
    if model:
        cfg["model"] = model
    print("=" * 60)
    print("Echo 工具调用测试 · 模型：%s" % cfg["model"])
    print("=" * 60)

    passed, failed, details = 0, 0, []
    for i, case in enumerate(CASES, 1):
        active = tools.select_tools(case["in"])
        chosen, args = None, ""
        try:
            msg = llm.call_llm(cfg, [{"role": "user", "content": case["in"]}],
                               active, temperature=0.2)
            calls = msg.get("tool_calls") or []
            if calls:
                chosen = calls[0]["function"]["name"]
                args = calls[0]["function"].get("arguments", "")
            else:
                chosen, args = _parse_text_call(msg.get("content"))
        except Exception as e:
            chosen = "出错:%s" % e

        ok = chosen in case["expect"]
        if ok:
            passed += 1
            print("  ✅ %2d. %-28s → %s" % (i, case["in"][:28], chosen))
        else:
            failed += 1
            print("  ❌ %2d. %-28s → %s（期望 %s）" % (
                i, case["in"][:28], chosen, "/".join(case["expect"])))
            details.append({"input": case["in"], "got": chosen, "expect": case["expect"]})

    total = passed + failed
    rate = (100.0 * passed / total) if total else 0
    print("-" * 60)
    print("通过 %d / %d（%.1f%%）" % (passed, total, rate))
    if details:
        print("\n失败明细（这些就是它现在的能力缺口）：")
        for d in details:
            print("  - %-30s 实际=%s 期望=%s" % (d["input"][:30], d["got"], "/".join(d["expect"])))
    print("=" * 60)
    return rate


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
