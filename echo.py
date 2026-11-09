# -*- coding: utf-8 -*-
"""
Echo（回声）—— 一个真正能自己干活的本地 AI Agent
================================================
和聊天助手的区别：你说目标，它自己规划步骤、自己动手（跑命令、
读写文件、查网页、检索知识库），看结果、再决定下一步，干完才汇报。

它完全跑在你自己的电脑上：
  大脑 = 本地 Ollama 开源模型（换模型改 config.json 一行）
  双手 = core/tools.py 里的工具
  记忆 = data/ 文件夹（重启不丢）
  知识 = kb/ 文件夹 + RAG 检索（改完 /reindex 生效）

启动：双击 启动.bat    退出：/exit    求助：/help
"""
import json
import os
import sys

from core import llm, memory, rag, tools

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOCAL_CONFIG_PATH = os.path.join(BASE_DIR, "config.local.json")
PERSONA_PATH = os.path.join(BASE_DIR, "persona.md")

MAX_STEPS = 20   # 一项任务最多自主走 20 步，防止停不下来


def load_config():
    default = {
        "api_base": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "qwen2.5:7b",
        "kb_dirs": ["kb"],
        "auto_confirm": False
    }
    cfg = dict(default)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    # 本地专属配置（个人路径等隐私，不进 git），覆盖 config.json
    if os.path.exists(LOCAL_CONFIG_PATH):
        with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    for k, v in default.items():
        cfg.setdefault(k, v)
    return cfg


def build_system(cfg):
    parts = []
    if os.path.exists(PERSONA_PATH):
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            parts.append(f.read())
    parts.append("当前时间：%s" % memory.now_str())
    facts = memory.load_facts()
    if facts:
        parts.append("关于用户的长期记忆（最近 20 条）：" +
                     "；".join(f["text"] for f in facts[-20:]))
    todos = [t for t in memory.load_todos() if not t["done"]]
    if todos:
        parts.append("用户未完成的待办：" +
                     "；".join("[%d]%s" % (t["id"], t["task"]) for t in todos))
    return "\n\n".join(parts)


def confirm(prompt):
    """危险操作前向用户要确认。"""
    ans = input("\n  ⚠ 需要你确认 — %s\n  执行吗？(y=同意 / 其他=拒绝) > " % prompt)
    return ans.strip().lower() in ("y", "yes", "好", "是")


def local_command(user, cfg):
    """本地指令（不经过大脑，秒回）。返回 True 表示已处理。"""
    if not user.startswith("/"):
        return False   # 不是指令，交给大脑去干
    cmd = user.split()[0].lower()
    arg = user[len(cmd):].strip()
    if cmd in ("/exit", "/quit"):
        print("回声> 记忆已保存，再见～")
        return "EXIT"
    if cmd == "/help":
        print(HELP_TEXT)
    elif cmd == "/time":
        print("回声> " + memory.now_str())
    elif cmd == "/auto":
        cfg["auto_confirm"] = not cfg["auto_confirm"]
        tools.ctx["auto"] = cfg["auto_confirm"]
        print("回声> 自动确认已 %s（危险命令%s问你）" % (
            "开启" if cfg["auto_confirm"] else "关闭",
            "不再" if cfg["auto_confirm"] else "会"))
    elif cmd == "/model":
        if arg:
            cfg["model"] = arg
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                base = json.load(f)
            base["model"] = arg   # 只改 config.json 的 model，不把本地隐私路径写进去
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(base, f, ensure_ascii=False, indent=2)
            print("回声> 大脑已切换为 %s" % arg)
        else:
            print("回声> 当前模型：%s。用法：/model 模型名（如 qwen2.5:14b）" % cfg["model"])
    elif cmd == "/memory":
        facts = memory.load_facts()
        if not facts:
            print("回声> 还没有记忆，说'记住：xxx'即可")
        for f in facts:
            print("  · (%s) %s" % (f["date"], f["text"]))
    elif cmd == "/forgetall":
        memory._save(memory.FACTS_PATH, [])
        print("回声> 记忆已清空。")
    elif cmd == "/remember":
        print("回声> " + memory.add_fact(arg) if arg else "回声> 用法：/remember 内容")
    elif cmd == "/todo":
        for t in memory.load_todos():
            print("  %s [%d] %s" % ("✔" if t["done"] else "□", t["id"], t["task"]))
    elif cmd == "/addtodo":
        print("回声> " + memory.add_todo(arg) if arg else "回声> 用法：/addtodo 内容")
    elif cmd == "/done":
        print("回声> " + memory.finish_todo(int(arg)) if arg.isdigit() else "回声> 用法：/done 编号")
    elif cmd == "/reindex":
        kb_dirs = [os.path.join(BASE_DIR, d) for d in cfg.get("kb_dirs", ["kb"])]
        print("回声> " + rag.build_index(kb_dirs))
    elif cmd == "/reset":
        memory.save_history([])
        print("回声> 对话历史已清空。")
    else:
        print("回声> 不认识这个指令，/help 看看。")
    return True


HELP_TEXT = """可用指令：
  /auto            切换危险命令自动确认（新手别开）
  /model 名字      换大脑模型（如 /model qwen2.5:14b）
  /reindex         重建知识库索引（kb/ 改动后用）
  /time /memory /remember /forgetall /todo /addtodo /done /reset /exit

直接说任务就行，例如：
  "帮我在 workspace 里写一个网页版贪吃蛇，写完自己测试"
  "看看 kb 知识库里关于 X 的内容，总结给我"
  "抓取 https://xxx 的正文，把要点存成笔记"
  "记住：我每周五有英语课" """


def chat(cfg):
    tools.ctx["auto"] = cfg.get("auto_confirm", False)
    tools.ctx["confirm_fn"] = confirm
    history = memory.load_history()
    print("=" * 50)
    print("  Echo 回声 · 本地自主 Agent")
    print("  说目标，我自己干；/help 求助；/exit 退出")
    print("  大脑：%s    知识库：kb/（/reindex 建索引）" % cfg["model"])
    print("=" * 50)

    while True:
        due = memory.check_reminders()
        for text in due:
            print("\n  ⏰ 提醒：%s" % text)
        try:
            user = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n回声> 再见～")
            break
        if not user:
            continue

        result = local_command(user, cfg)
        if result == "EXIT":
            break
        if result:
            memory.check_reminders()
            continue

        # ===== 自主任务循环（agent 的心脏）=====
        content = user
        if "知识库" in user:   # 提到知识库就自动先检索，不指望模型自觉
            kb_hit = rag.search(user)
            if not kb_hit.startswith(("知识库", "检索失败")):
                content = user + "\n\n[知识库检索结果（回答必须基于此内容）]\n" + kb_hit
        history.append({"role": "user", "content": content})
        messages = [{"role": "system", "content": build_system(cfg)}] + history[-30:]
        try:
            for step in range(1, MAX_STEPS + 1):
                msg = llm.call_llm(cfg, messages, tools.TOOLS)
                calls = msg.get("tool_calls")
                if not calls:
                    reply = (msg.get("content") or "……").strip()
                    print("\n回声> " + reply)
                    history.append({"role": "assistant", "content": reply})
                    break
                messages.append(msg)
                for tc in calls:
                    fn = tc["function"]
                    argstr = fn.get("arguments") or "{}"
                    try:
                        args = json.loads(argstr)
                    except Exception:
                        args = {}
                    print("  [第%d步] %s(%s)" % (step, fn["name"],
                                                 _brief(argstr)))
                    result = tools.run_tool(fn["name"], args)
                    messages.append({"role": "tool",
                                     "tool_call_id": tc.get("id", ""),
                                     "content": str(result)})
            else:
                print("\n回声> 走满了 %d 步还没收工，先停下来汇报。"
                      "可以说'继续'让我接着干。" % MAX_STEPS)
        except Exception as e:
            print("回声> 出错了：%s" % e)
            print("       若是连不上大脑：确认 Ollama 在跑（ollama serve），"
                  "模型存在（ollama list）")
        memory.save_history(history)


def _brief(s, limit=80):
    s = s.replace("\n", " ")
    return s if len(s) <= limit else s[:limit] + "…"


if __name__ == "__main__":
    chat(load_config())
