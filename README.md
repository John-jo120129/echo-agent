# Echo 回声 —— 完全跑在你自己电脑上的 AI Agent

> 你喊一声，必有回应。
> 不依赖云端、不上传数据、断网可用、代码全开源。

**它不是聊天机器人，是真正会自己干活的 Agent。** 你说目标，它自己拆步骤、自己动手（跑命令、读写文件、抓网页、操控鼠标键盘），看结果、自己纠错，干完才向你汇报。

---

## 🚀 三步开始（Windows）

### 1. 装两个东西
| 需要 | 在哪装 | 注意 |
|------|--------|------|
| **[Python 3.10+](https://www.python.org/downloads/)** | 官网 | 安装时**一定勾选** `Add Python to PATH` |
| **[Ollama](https://ollama.com)** | 官网 | 装完它会在后台常驻 |

### 2. 下载本项目
- **方式 A（推荐）**：在本页点绿色 `Code` → `Download ZIP` → 解压
- **方式 B**：`git clone https://github.com/John-jo120129/echo-agent.git`

### 3. 双击安装，再双击启动
```
双击 安装.bat        ← 自动装依赖、检查 Ollama、可选下模型
双击 启动.bat        ← 命令行版
双击 启动网页版.bat   ← 网页版（浏览器里聊，推荐）
```

网页版打开后访问 **http://127.0.0.1:8899**

> 第一次用网页版如果提示缺浏览器内核，跑一次：`python -m playwright install chromium`

---

## 💡 它能干什么

**说人话，它自己干：**

```
你：帮我写个脚本打印 1 到 100 的和，写完自己跑一遍验证
回声：[第1步] write_file(calc.py)
      [第2步] run_command(python calc.py)   ← 发现写错了
      [第3步] write_file(重写)               ← 自己发现、自己改
      [第4步] run_command(python calc.py)   → 5050 ✓
      已完成，结果 5050，文件在 workspace/calc.py
```

**能力清单：**

| 类别 | 能干什么 |
|------|---------|
| 🔧 **动手** | 执行命令、读写文件、列目录、搜文件 |
| 🖱️ **控电脑** | 截屏、OCR 读屏、读控件坐标、鼠标点击/双击/拖动、键盘输入 |
| 🌐 **上网** | 搜全网、抓网页正文、Playwright 操作浏览器（点按钮、填表、截图）|
| 👀 **看图** | 截屏发给视觉模型真"看懂"画面（需 `qwen2.5vl:7b`）|
| 🎬 **看视频** | 采样关键帧理解视频内容和动作（不是逐帧）|
| 🎤 **语音** | 说话输入（本地 whisper 转文字）、朗读回复（edge-tts）|
| 🧠 **记忆** | 长期记忆、用户画像、知识库 RAG、技能自动沉淀 |
| ⏰ **定时** | `/schedule 08:00 汇报天气`，到点自动干 |
| 🔁 **多 Agent** | 每个任务走「规划 → 执行 → 反思」三阶段 |

**安全设计：**
- 危险命令（删除/格式化/关机）必须你按 `y` 确认
- 往项目外写文件要确认
- 每次工具调用都记日志，`/log` 可回看
- 改自己代码前自动备份，改坏了能恢复

---

## ⌨️ 常用命令

| 命令 | 作用 |
|------|------|
| `/help` | 全部指令 |
| `/model qwen2.5:14b` | 换大脑模型 |
| `/listen` | 语音输入 |
| `/speak_auto` | 回复自动朗读 |
| `/multi` | 开关多 Agent（规划/执行/反思）|
| `/tasks` | 看最近做了什么 |
| `/log` | 看操作日志 |
| `/star` | 3D 记忆星球 |
| `/reindex` | 重建知识库索引 |
| `/exit` | 退出 |

---

## ❓ 常见问题

### 双击 bat 出现一堆"不是内部或外部命令"
**原因**：txt 编辑器把文件存成了 UTF-8 / 改了换行，Windows 批处理解析崩了。

**解决**：
1. 重新下载（别用记事本打开再保存）
2. 或者直接命令行跑：`python echo.py`

> 我们的 bat 已经写成纯 ASCII 单行，正常下载不会出这个问题。

### 提示 `python 不是内部或外部命令`
Python 没装或没勾选 `Add Python to PATH`。重装时勾上，或改用 `py` 命令。

### 提示连不上模型 / 大脑离线
Ollama 没启动。终端执行：
```
ollama serve
```
或重启 Ollama。

### 模型没下载
```
ollama pull qwen2.5:7b          # 大脑（必装，4.7G）
ollama pull mxbai-embed-large   # 知识库向量（0.7G）
ollama pull qwen2.5vl:7b        # 看图/视频（可选，6G）
```

### 卡 / 慢
- 8G 显存跑 7b 刚好，14b 会有一半跑 CPU（慢但更聪明）
- 换模型：`/model qwen2.5:7b`

---

## 🧱 技术栈

| 层 | 用什么 |
|----|--------|
| 大脑 | 本地 Ollama（任意 OpenAI 兼容 API 都能换）|
| 编排 | 自己写的（零框架依赖，核心只用标准库）|
| 电脑操控 | pyautogui + uiautomation（Windows UI Automation，不吃显卡）|
| 浏览器 | Playwright（复用系统 Edge，免下载内核）|
| 语音 | faster-whisper（听）+ edge-tts（说）|
| 界面 | 原生 HTML/CSS/JS + Python HTTP 服务（SSE 流式）|

**项目结构：**
```
echo-agent/
├── echo.py            # 命令行入口
├── webui.py           # 网页版入口
├── desktop.py         # 桌面 exe 入口
├── install.py         # 一键安装
├── core/
│   ├── agent.py       # 主循环（规划-执行-反思）
│   ├── llm.py         # 模型接口
│   ├── tools.py       # 工具集（30+ 个）
│   ├── memory.py      # 记忆
│   ├── skills.py      # 技能加载
│   ├── taskstore.py   # 任务持久化
│   ├── computer.py    # 电脑操控
│   ├── browser.py     # 浏览器
│   └── ...
├── skills/            # 技能（自动沉淀的也在里面）
├── kb/                # 知识库（丢 .md 进去就行）
└── tests.py           # 工具调用测试集（20 条）
```

---

## 📜 License

MIT —— 随便用、随便改、随便发。

---

> 山谷里喊一声，必有回音。
