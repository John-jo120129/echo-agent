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

from core import agent, llm, tools   # noqa: E402

# 每条：输入 → 期望调用哪个工具（允许多个，因为有些说法本身有歧义）
CASES = [
    {"in": "打开记事本", "expect": ["open_app"]},
    {"in": "双击桌面上的 Blender 图标", "expect": ["mouse_double"]},
    {"in": "看看我的屏幕上有什么", "expect": ["read_screen", "view_screen"]},
    {"in": "把「你好」保存到文件 D:/echo-agent/workspace/a.txt", "expect": ["write_file"]},
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
    # ---- 第二批：覆盖剩下的工具 ----
    {"in": "把 config.json 里的 14b 改成 7b", "expect": ["edit_file", "read_file"]},
    {"in": "在项目里搜一下哪个文件带 TODO 标记", "expect": ["search_files"]},
    {"in": "你还记得我喜欢什么吗", "expect": ["search_memory", "search_kb"]},
    {"in": "把这件事记成长期记忆：下周三要考试", "expect": ["remember_long", "remember"]},
    {"in": "记住我生日是 3 月 5 号", "expect": ["remember_profile", "remember"]},
    {"in": "现在有哪些技能可以用", "expect": ["list_skills"]},
    {"in": "加载数据分析技能", "expect": ["use_skill", "list_skills"]},
    {"in": "加个待办：明天交作业", "expect": ["add_todo"]},
    {"in": "写篇日记：今天有点累", "expect": ["write_diary"]},
    {"in": "20 分钟后提醒我喝水", "expect": ["set_reminder"]},
    {"in": "截个屏", "expect": ["screenshot", "read_screen"]},
    {"in": "看看当前窗口有哪些按钮", "expect": ["read_controls"]},
    {"in": "列出这个网页上能点的东西", "expect": ["browser_get_elements"]},
    {"in": "问我选哪个方案，选项给：方案A、方案B", "expect": ["ask_user"]},
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
    sys_prompt = agent.build_system(cfg)   # 带上完整人格，贴近真实运行环境
    for i, case in enumerate(CASES, 1):
        active = tools.select_tools(case["in"])
        chosen, args = None, ""
        try:
            msg = llm.call_llm(cfg, [{"role": "system", "content": sys_prompt},
                                     {"role": "user", "content": case["in"]}],
                               active, temperature=0.0)
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
