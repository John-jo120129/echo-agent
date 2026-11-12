# -*- coding: utf-8 -*-
"""tests_e2e.py —— 端到端测试（mock 模型，验证 agent 主循环逻辑）

不依赖真实大模型：跑得快（秒级）、结果稳定，可以当回归测试。
跑法：python tests_e2e.py
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from core import agent, tools   # noqa: E402

with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)
CFG["multi_agent"] = False     # 关掉规划/反思，简化调用序列
CFG["auto_skill"] = False      # 测试时不写技能文件
CFG["auto_fact"] = False       # 测试时不写记忆


def reply(text):
    return {"content": text, "tool_calls": None}


def call(name, args=None):
    return {"content": "", "tool_calls": [{
        "id": "c1",
        "function": {"name": name, "arguments": json.dumps(args or {}, ensure_ascii=False)},
    }]}


class TestAgentLoop(unittest.TestCase):
    """agent 主循环：各种情况都应稳稳跑完、不崩、不无脑循环。"""

    def test_simple_reply(self):
        """模型直接回复，不调工具"""
        with patch("core.llm.call_llm", return_value=reply("你好，我是回声")):
            events = []
            r = agent.run_agent(CFG, "你好", [], events.append)
        self.assertIn("回声", r)
        self.assertTrue(any(e.get("type") == "reply" for e in events))

    def test_tool_then_reply(self):
        """先调工具，再给回复"""
        seq = [call("get_time"), reply("现在是测试时间")]
        with patch("core.llm.call_llm", side_effect=seq):
            events = []
            r = agent.run_agent(CFG, "现在几点", [], events.append)
        self.assertIn("测试时间", r)
        self.assertTrue(any(e.get("type") == "step" for e in events))

    def test_unknown_tool(self):
        """模型编了个不存在的工具名，应被兜住而不是崩"""
        seq = [call("nonexistent_tool_xyz"), reply("工具不存在，我换个办法")]
        with patch("core.llm.call_llm", side_effect=seq):
            r = agent.run_agent(CFG, "用不存在的工具", [], lambda e: None)
        self.assertIn("换个办法", r)

    def test_tool_error_continues(self):
        """工具执行报错后，模型还能继续"""
        seq = [call("read_file", {"path": "D:/绝对不存在/xx.txt"}), reply("文件读不到，我换个思路")]
        with patch("core.llm.call_llm", side_effect=seq):
            r = agent.run_agent(CFG, "读个不存在的文件", [], lambda e: None)
        self.assertIn("换个思路", r)

    def test_max_steps_stops(self):
        """一直调工具不结束 → 到上限必须停，不能死循环"""
        seq = [call("get_time")] * 20
        with patch("core.llm.call_llm", side_effect=seq):
            events = []
            r = agent.run_agent(CFG, "无限循环", [], events.append, max_steps=3)
        self.assertTrue(any("步" in str(e.get("text", "")) for e in events))

    def test_llm_offline(self):
        """模型连不上 → 友好提示，不抛异常"""
        with patch("core.llm.call_llm", side_effect=Exception("connection refused")):
            events = []
            r = agent.run_agent(CFG, "你好", [], events.append)
        self.assertTrue(len(r) > 0 or any(e.get("type") == "reply" for e in events))


class TestSafety(unittest.TestCase):
    """安全底线：危险操作必须被拦。"""

    def test_dangerous_rejected_when_not_auto(self):
        tools.ctx["auto"] = False
        tools.ctx["confirm_fn"] = lambda p: False
        result = tools.run_tool("run_command", {"command": "del /f /s /q D:\\test_xyz"})
        self.assertIn("拒绝", str(result))

    def test_dangerous_allowed_when_confirmed(self):
        tools.ctx["auto"] = False
        tools.ctx["confirm_fn"] = lambda p: True
        result = tools.run_tool("run_command", {"command": "echo safe_test"})
        self.assertIn("safe_test", str(result))
        tools.ctx["confirm_fn"] = lambda p: False   # 还原


class TestToolsBasics(unittest.TestCase):
    """工具层的基本正确性（不依赖模型）。"""

    def test_get_time(self):
        self.assertRegex(tools.run_tool("get_time", {}), r"\d{4}")

    def test_list_dir(self):
        out = tools.run_tool("list_dir", {"path": BASE})
        self.assertIn("webui.py", out)

    def test_write_read_roundtrip(self):
        # 用 workspace 下的文件（项目内，不需要确认弹窗）
        p = os.path.join(BASE, "workspace", "_e2e_test.txt")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tools.run_tool("write_file", {"path": p, "content": "hello-e2e"})
        self.assertIn("hello-e2e", tools.run_tool("read_file", {"path": p}))
        try:
            os.remove(p)
        except Exception:
            pass

    def test_select_tools_skill(self):
        names = [t["function"]["name"] for t in tools.select_tools("加载数据分析技能")]
        self.assertIn("use_skill", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
