# -*- coding: utf-8 -*-
"""mcp_server.py —— 把 Echo 的能力暴露成 MCP 服务

这样 Claude Desktop / Cursor / 任何 MCP 客户端都能直接调用 Echo 的工具
（读文件、搜网页、操作浏览器、操控电脑……）。

用法：
  1. 独立测试：python mcp_server.py（会等 MCP 客户端连接，Ctrl+C 退出）
  2. 在 MCP 客户端配置里加（示例，Claude Desktop 的 claude_desktop_config.json）：
     {
       "mcpServers": {
         "echo": {
           "command": "python",
           "args": ["D:/echo-agent/mcp_server.py"]
         }
       }
     }

安全说明：只暴露"读类/查询类"和少量明确操作，不暴露 run_command（任意命令执行）。
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from mcp.server.mcpserver import MCPServer   # noqa: E402

from core import tools                       # noqa: E402

server = MCPServer("echo", version="1.1")


# ---------- 文件 ----------
@server.tool(description="读本地文件内容")
def read_file(path: str) -> str:
    return str(tools.run_tool("read_file", {"path": path}))


@server.tool(description="列出目录下的文件（最多两层）")
def list_dir(path: str = ".") -> str:
    return str(tools.run_tool("list_dir", {"path": path}))


@server.tool(description="把内容保存到本地文件（新建或覆盖）")
def write_file(path: str, content: str) -> str:
    return str(tools.run_tool("write_file", {"path": path, "content": content}))


@server.tool(description="在文件里搜索包含关键字的行")
def search_files(path: str, keyword: str) -> str:
    return str(tools.run_tool("search_files", {"path": path, "keyword": keyword}))


# ---------- 网络 ----------
@server.tool(description="联网搜索（必应），返回标题+链接+摘要")
def web_search(query: str) -> str:
    return str(tools.run_tool("web_search", {"query": query}))


@server.tool(description="抓取网页正文（已标注为不可信数据）")
def web_fetch(url: str) -> str:
    return str(tools.run_tool("web_fetch", {"url": url}))


# ---------- 浏览器 ----------
@server.tool(description="用浏览器打开网页")
def browser_open(url: str) -> str:
    return str(tools.run_tool("browser_open", {"url": url}))


@server.tool(description="列出当前网页所有可点击元素（文字+标签+坐标）")
def browser_get_elements() -> str:
    return str(tools.run_tool("browser_get_elements", {}))


@server.tool(description="点击网页上的元素（文字或 CSS 选择器）")
def browser_click(target: str) -> str:
    return str(tools.run_tool("browser_click", {"target": target}))


@server.tool(description="读当前网页正文")
def browser_read() -> str:
    return str(tools.run_tool("browser_read", {}))


# ---------- 电脑 ----------
@server.tool(description="打开一个程序（如 notepad、wps、微信）")
def open_app(name: str) -> str:
    return str(tools.run_tool("open_app", {"name": name}))


@server.tool(description="截屏并返回屏幕上的文字（OCR）")
def read_screen() -> str:
    return str(tools.run_tool("read_screen", {}))


@server.tool(description="双击桌面图标（传图标文字，自动找位置）")
def mouse_double(target: str) -> str:
    return str(tools.run_tool("mouse_double", {"target": target}))


# ---------- 记忆 ----------
@server.tool(description="搜索 Echo 的长期记忆和知识库")
def search_memory(query: str) -> str:
    return str(tools.run_tool("search_kb", {"query": query}))


@server.tool(description="往长期记忆里记一条（用户偏好、事实等）")
def remember(text: str) -> str:
    return str(tools.run_tool("remember", {"text": text}))


@server.tool(description="获取当前日期时间")
def get_time() -> str:
    return str(tools.run_tool("get_time", {}))


if __name__ == "__main__":
    print("Echo MCP Server 启动中（stdio）... 在 MCP 客户端里配置本文件即可", file=sys.stderr)
    server.run(transport="stdio")
