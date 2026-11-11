# -*- coding: utf-8 -*-
"""core/agent.py —— Agent 核心循环（多角色协作）

一个任务进来，分三个阶段，像一个小团队协作：
  1. 规划（规划师 Planner）—— 先想清楚怎么做，输出简短计划
  2. 执行（执行者 Executor）—— 按计划调用工具干活，最多 N 步自我纠错
  3. 反思（审阅员 Reviewer）—— 检查结果是否达成目标，没达成就继续

命令行（echo.py）和网页版（webui.py）都调用 run_agent，只是 emit 方式不同。
"""
import json
import os
import re

from core import llm, memory, rag, skills, tools

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONA_PATH = os.path.join(BASE_DIR, "persona.md")
MAX_STEPS = 20


def build_system(cfg):
    """分层注入：人设 → 用户档案 → 长期记忆 → 短期记忆 → 待办 → 技能摘要。"""
    parts = []
    if os.path.exists(PERSONA_PATH):
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            parts.append(f.read())
    parts.append("当前时间：%s" % memory.now_str())
    home = os.path.expanduser("~")
    parts.append("当前用户目录：%s（桌面=%s，下载=%s，文档=%s）。"
                 "用户说'桌面/下载/文档'时直接用这些路径，别反复问路径，先列目录看结果。"
                 % (home, os.path.join(home, "Desktop"),
                    os.path.join(home, "Downloads"), os.path.join(home, "Documents")))

    profile = memory.load_profile()
    if profile:
        parts.append("【用户档案】" + "；".join("%s=%s" % (k, v) for k, v in profile.items()))

    long_term = memory.load_long_term()
    if long_term:
        parts.append("【长期记忆】" + "；".join(
            "(%s)%s" % (l["date"], l["text"]) for l in long_term[-20:]))

    facts = memory.load_facts()
    if facts:
        parts.append("【短期记忆】" + "；".join(f["text"] for f in facts[-20:]))

    todos = [t for t in memory.load_todos() if not t["done"]]
    if todos:
        parts.append("用户未完成的待办：" +
                     "；".join("[%d]%s" % (t["id"], t["task"]) for t in todos))

    sk = skills.list_skills()
    if sk:
        parts.append("【可用技能】做专业任务前先 list_skills 或 use_skill 加载规范：\n" +
                     "\n".join("- %s：%s（%s）" % (s["name"], s["description"], s["when"])
                               for s in sk))

    return "\n\n".join(parts)


def _inject_knowledge(user):
    """用户提到知识库/记忆/之前 时，自动检索相关资料注入。"""
    if not any(w in user for w in ("知识库", "记忆", "说过", "之前", "还记得")):
        return user
    try:
        hit = rag.search(user)
        if hit and not hit.startswith(("知识库", "检索失败")):
            return user + "\n\n[检索到的相关资料（回答必须基于此内容，找不到就说没有）]\n" + hit
    except Exception:
        pass
    return user


def _tool_failed(result):
    """工具结果里带这些词，就认为失败了，值得让模型修正重试。"""
    return any(w in str(result) for w in
               ("失败", "错误", "读不了", "不存在", "没找到", "拒绝", "出错", "缺少", "不允许"))


def _compress_history(cfg, history):
    """history 太长时，把早期对话压缩成摘要（而不是硬截断丢信息）。

    参考 RECAP/TencentDB Agent Memory 的思路：瓶颈从"模型能记多少"转移到"摘要写得好不好"。
    """
    if len(history) <= 24:
        return history
    old = history[:-12]
    recent = history[-12:]
    lines = []
    for m in old:
        role = "用户" if m.get("role") == "user" else "AI"
        text = (m.get("content") or "").strip()
        if text:
            lines.append("%s：%s" % (role, text[:150]))
    if not lines:
        return history[-24:]
    try:
        r = llm.call_llm(cfg, [{"role": "user", "content":
            "把下面这段早前对话压缩成一段简短摘要（150 字内）。"
            "只保留：用户的关键信息/偏好、已完成的事、重要结论。不要编造。\n\n"
            + "\n".join(lines)}], tools=[])
        summary = (r.get("content") or "").strip()
        if summary:
            return [{"role": "system", "content": "【早前对话摘要】" + summary}] + recent
    except Exception:
        pass
    return history[-24:]


def run_agent(cfg, user_input, history, emit, max_steps=None):
    """执行一次完整任务，emit(event) 推送过程事件。返回最终回复文本。"""
    max_steps = max_steps or MAX_STEPS
    multi = cfg.get("multi_agent", True)
    plan = ""
    content = _inject_knowledge(user_input)
    history.append({"role": "user", "content": content})

    # 快捷兜底：整句就是"打开/启动/运行 X"时，直接调 open_app（模型常绕路去找图标）
    m = re.match(r"^(?:帮我)?(?:打开|启动|运行)\s*([A-Za-z0-9\u4e00-\u9fa5]{1,20})\s*$",
                 user_input.strip())
    if m and m.group(1) not in ("文件", "文件夹", "目录", "这个", "那个", "它"):
        result = tools.run_tool("open_app", {"name": m.group(1)})
        emit({"type": "reply", "text": result})
        history.append({"role": "assistant", "content": result})
        return result

    messages = ([{"role": "system", "content": build_system(cfg)}]
                + _compress_history(cfg, history))

    # 阶段1：规划
    if multi:
        emit({"type": "phase", "text": "规划"})
        try:
            pm = llm.call_llm(cfg, messages + [{"role": "user", "content":
                "【规划】只输出你打算怎么做的思路（一句话，说清用什么工具/步骤），"
                "不要直接给出答案或结果。"}], tools=[])
            plan = (pm.get("content") or "").strip()
            if plan:
                emit({"type": "plan", "text": plan})
                messages.append({"role": "assistant", "content": "计划：" + plan})
                messages.append({"role": "user", "content":
                    "按上面的计划立刻开始执行，直接调用工具行动，不要问用户确认，也不要停在'我打算…'就结束。"})
        except Exception:
            pass

    # 阶段2：执行
    reviewed = False
    auth_retried = False
    call_history = []
    active_tools = tools.select_tools(user_input)   # 按意图挑工具，给小模型减负
    for step in range(1, max_steps + 1):
        msg = llm.call_llm(cfg, messages, active_tools,
                           on_token=lambda t: emit({"type": "token", "text": t}),
                           temperature=0.2)   # 工具调用用低温，减少格式漂移
        calls = msg.get("tool_calls")
        if not calls:
            reply = (msg.get("content") or "").strip()

            # 兜底：模型没调工具、却在问"请允许/请确认/请提供坐标" → 注入授权，逼它动手一次
            if reply and not auth_retried and any(
                    w in reply for w in ("请允许", "请确认", "是否允许", "请提供", "允许我", "需要你授权")):
                auth_retried = True
                emit({"type": "plan", "text": "（自动授权：直接执行）"})
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content":
                    "用户已授予你截屏、鼠标、键盘的完整系统权限，不要再问任何确认，"
                    "立刻调用合适的工具（read_controls/view_screen/mouse_double 等）直接执行。"})
                continue

            # 兜底：有些小模型（如 7b）不会用标准 tool_calls，会把工具调用写成 JSON 文本
            # 形如 {"name": "read_screen", "arguments": {}} —— 替它解析并执行
            m = re.search(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}',
                          reply, re.S)
            if m:
                tool_name, raw_args = m.group(1), m.group(2)
                try:
                    targs = json.loads(raw_args)
                except Exception:
                    targs = {}
                if tool_name in tools._IMPL:
                    key = tool_name + "|" + raw_args
                    # 熔断：同一个工具同参数连续重复，说明模型卡住了，别再空转
                    if call_history.count(key) >= 2:
                        msg_txt = "（%s 反复执行同样的操作、结果没变化，我先停下。）" % tool_name
                        emit({"type": "reply", "text": msg_txt})
                        history.append({"role": "assistant", "content": msg_txt})
                        return msg_txt
                    call_history.append(key)
                    emit({"type": "step", "step": step, "tool": tool_name,
                          "args": raw_args[:80]})
                    result = tools.run_tool(tool_name, targs)
                    messages.append({"role": "assistant", "content": reply})
                    if _tool_failed(result):
                        messages.append({"role": "user", "content":
                            "工具 %s 执行失败：%s\n请检查参数（路径/内容是否正确），修正后重试，或换一个方法。"
                            % (tool_name, result)})
                    else:
                        messages.append({"role": "user",
                                         "content": "工具 %s 执行结果：%s" % (tool_name, result)})
                    continue

            # 兜底：主循环没内容时，用规划阶段的文本（模型可能把话都说在计划里了）
            if not reply and plan:
                reply = plan
                emit({"type": "token", "text": reply})

            # 阶段3：反思（多 agent 时，只反思一次，避免死循环）
            if multi and reply and not reviewed:
                reviewed = True
                emit({"type": "phase", "text": "反思"})
                try:
                    rm = llm.call_llm(cfg, messages + [
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content":
                         "【反思】检查上面的结果是否已完整达成用户目标。"
                         "已达成只回「完成」；没达成回「继续：还差什么」（一句话说清）。"}], tools=[])
                    review = (rm.get("content") or "").strip()
                    emit({"type": "review", "text": review})
                    if review.startswith("继续") and step < max_steps:
                        messages.append({"role": "user", "content": "还没完成，请继续：" + review})
                        continue
                except Exception:
                    pass

            emit({"type": "reply", "text": reply or "……"})
            history.append({"role": "assistant", "content": reply})
            return reply

        messages.append(msg)
        for tc in calls:
            fn = tc["function"]
            argstr = fn.get("arguments") or "{}"
            try:
                args = json.loads(argstr)
            except Exception:
                args = {}
            emit({"type": "step", "step": step, "tool": fn["name"], "args": argstr})
            result = tools.run_tool(fn["name"], args)
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": str(result)})
            if _tool_failed(result):
                messages.append({"role": "user", "content":
                    "工具 %s 执行失败（见上面结果），请检查参数后重试，或换一个方法。" % fn["name"]})

    emit({"type": "reply", "text": "走了 %d 步还没完成，先停下汇报，可以说「继续」。" % max_steps})
    return ""
