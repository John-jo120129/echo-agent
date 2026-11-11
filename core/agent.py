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

from core import llm, memory, rag, skills, tools, taskstore

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


def _extract_facts(cfg, user_input, reply):
    """任务完成后，从对话里提取值得长期记住的事实/偏好（L1）。

    保守策略：只提取用户明确说过的，没有就跳过。add_fact 自带去重。
    """
    try:
        r = llm.call_llm(cfg, [{"role": "user", "content":
            "从下面这轮对话里提取值得长期记住的事实或偏好（用户的名字/喜好/习惯/正在做的事）。\n"
            "只提取明确说过的，不要猜、不要编。每条一行用「- 」开头；没有就只输出「无」。\n\n"
            "用户：%s\nAI：%s" % (user_input[:300], (reply or "")[:300])}],
            tools=[], temperature=0.2)
        text = (r.get("content") or "").strip()
        if not text or text.strip() == "无":
            return 0
        added = 0
        for line in text.splitlines():
            line = line.strip().lstrip("-·*• ").strip()
            if line and line != "无" and 4 <= len(line) <= 100:
                if "已记住" in memory.add_fact(line):
                    added += 1
        return added
    except Exception:
        return 0


def _record_lesson(cfg, user_input, call_log):
    """任务没干成 → 让模型总结教训写进长期记忆，下次别再踩同样的坑。

    参考 Reflexion / CamoClaw：失败经验只有被写下来、下次能读到，才算"学习"。
    """
    if not call_log:
        return
    steps = "\n".join("- %s(%s) → %s" % (c["tool"], c["args"][:60], str(c["result"])[:80])
                      for c in call_log[-10:])
    try:
        r = llm.call_llm(cfg, [{"role": "user", "content":
            "下面这个任务没完成。请用一句话总结：失败原因 + 下次该怎么做。"
            "直接给结论，不要客套。\n\n任务：%s\n\n执行记录：\n%s"
            % (user_input, steps)}], tools=[], temperature=0.3)
        lesson = (r.get("content") or "").strip()
        if lesson and len(lesson) > 10:
            memory.add_long_term("[教训] " + lesson[:200], kind="lesson")
    except Exception:
        pass


def _maybe_save_skill(cfg, user_input, call_log, reply):
    """成功完成的多步任务（>=3 次工具调用）→ 自动沉淀成技能。

    参考 Hermes Agent：任务做完就把步骤、坑、验证方法写成 SKILL.md，
    下次遇到类似任务能直接复用，不用从零试错。
    """
    if len(call_log) < 3:
        return None
    steps = "\n".join("- %s(%s) → %s" % (c["tool"], c["args"], c["result"])
                      for c in call_log)
    try:
        r = llm.call_llm(cfg, [{"role": "user", "content":
            "下面是一次成功完成的任务。请把它总结成一个可复用的技能，"
            "直接输出 markdown（不要用代码块包裹），格式：\n"
            "# 技能名\n## 适用场景\n## 步骤\n## 注意事项\n\n"
            "任务：%s\n\n执行记录：\n%s" % (user_input, steps)}], tools=[])
        md = (r.get("content") or "").strip()
        if not md or len(md) < 80:
            return None
        # 模型常忘了写 front matter，缺了它技能列表里就只有名字没有描述。
        # 这里程序补一个：从正文里抠标题和"适用场景"。
        if not md.startswith("---"):
            lines = md.splitlines()
            title, desc = "", ""
            for i, ln in enumerate(lines):
                if ln.startswith("# ") and not title:
                    title = ln[2:].strip()
                if "适用" in ln and not desc and i + 1 < len(lines):
                    desc = lines[i + 1].strip()
            title = title or "自动技能"
            desc = (desc or title)[:60]
            md = ("---\nname: %s\ndescription: %s\nwhen_to_use: %s\n---\n\n%s"
                  % (title, desc, desc, md))
        first = (md.split("---")[1] if md.startswith("---") else "")
        m2 = re.search(r"name:\s*(.+)", first)
        name_hint = m2.group(1).strip() if m2 else ""
        if not name_hint:
            for ln in md.splitlines():
                if ln.startswith("# "):
                    name_hint = ln[2:].strip()
                    break
        slug = re.sub(r"[^\w\u4e00-\u9fa5]", "_", name_hint or "auto")[:24].strip("_") or "auto"
        d = os.path.join(BASE_DIR, "skills", "auto_" + slug)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "SKILL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return path
    except Exception:
        return None


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
    task_id = taskstore.start_task(user_input)   # 任务持久化：开跑就落盘
    content = _inject_knowledge(user_input)
    history.append({"role": "user", "content": content})

    # 快捷兜底：整句就是"打开/启动/运行 X"时，直接调 open_app（模型常绕路去找图标）
    m = re.match(r"^(?:帮我)?(?:打开|启动|运行)\s*([A-Za-z0-9\u4e00-\u9fa5]{1,20})\s*$",
                 user_input.strip())
    if m and m.group(1) not in ("文件", "文件夹", "目录", "这个", "那个", "它"):
        result = tools.run_tool("open_app", {"name": m.group(1)})
        emit({"type": "reply", "text": result})
        history.append({"role": "assistant", "content": result})
        taskstore.finish_task(task_id, "done", result)
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
                    "用户的原话是：「%s」。现在就按计划直接调用工具完成它，不要问确认，也不要停在'我打算…'。"
                    % user_input})
        except Exception:
            pass

    # 阶段2：执行
    reviewed = False
    auth_retried = False
    call_history = []
    call_log = []          # 本次任务的所有工具调用，用于沉淀技能
    active_tools = tools.select_tools(user_input)   # 按意图挑工具，给小模型减负
    for step in range(1, max_steps + 1):
        try:
            msg = llm.call_llm(cfg, messages, active_tools,
                               on_token=lambda t: emit({"type": "token", "text": t}),
                               temperature=0.2)   # 工具调用用低温，减少格式漂移
        except Exception as e:
            err = ("【大脑离线】连不上模型服务（%s）。\n"
                   "请检查 Ollama 是否在运行：打开终端执行 ollama serve，或重启 Ollama 后再试。") % e
            emit({"type": "reply", "text": err})
            history.append({"role": "assistant", "content": err})
            taskstore.finish_task(task_id, "failed", err)
            return err
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
                    call_log.append({"tool": tool_name, "args": raw_args[:120],
                                     "result": str(result)[:150]})
                    taskstore.update_task(task_id, step, call_log)
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
            # 技能沉淀：多步任务成功后自动总结成 SKILL.md（config 里 auto_skill=false 可关）
            if cfg.get("auto_skill", True):
                try:
                    _maybe_save_skill(cfg, user_input, call_log, reply)
                except Exception:
                    pass
            # 事实提炼：把对话里明确提到的偏好/信息记进长期记忆（config 里 auto_fact=false 可关）
            if cfg.get("auto_fact", True):
                try:
                    _extract_facts(cfg, user_input, reply)
                except Exception:
                    pass
            taskstore.finish_task(task_id, "done", reply)
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
            call_log.append({"tool": fn["name"], "args": argstr[:120],
                             "result": str(result)[:150]})
            taskstore.update_task(task_id, step, call_log)
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": str(result)})
            if _tool_failed(result):
                messages.append({"role": "user", "content":
                    "工具 %s 执行失败（见上面结果），请检查参数后重试，或换一个方法。" % fn["name"]})

    emit({"type": "reply", "text": "走了 %d 步还没完成，先停下汇报，可以说「继续」。" % max_steps})
    # 没干成 → 把教训记下来，下次别再踩
    try:
        _record_lesson(cfg, user_input, call_log)
    except Exception:
        pass
    taskstore.finish_task(task_id, "failed", "超过最大步数")
    return ""
