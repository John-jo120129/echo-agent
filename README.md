# Echo 回声 —— 完全跑在你自己电脑上的 AI Agent

> 你喊一声，必有回应。
>
> 不依赖任何云端服务、不上传任何数据、断网可用、代码全开源。

## 这是什么

一个**真正会自己干活的本地 AI Agent**，不是聊天机器人。

你说目标，它自己拆步骤、自己动手（跑命令、读写文件、抓网页、查知识库），
看结果、再决定下一步，干完才向你汇报：

```
你说: 帮我写一个脚本，功能是打印1到100的和，写完自己运行验证

回声: [第1步] write_file(workspace/calc.py)
      [第2步] run_command(python calc.py)   ← 发现转义写错了
      [第3步] write_file(重写)               ← 自己发现、自己改
      [第4步] run_command(python calc.py)   → 5050 ✓
      已完成，结果为 5050，文件在 workspace/calc.py
```

## 核心特性

- **自主任务循环**：最多 20 步，模型每步自己决定用什么工具、观察结果、自我纠错
- **真实工具**：执行命令、读写文件、列目录、搜文件、抓网页正文
- **RAG 知识库**：把 `.md` 文件放进 `kb/`，运行 `/reindex`，它就能答知识库里的问题
- **联网搜索**：本地知识库查不到的，自动用 `web_search` 搜全网（必应）+ `web_fetch` 抓正文
- **长期记忆**：说过的事、待办、日记存在本地 `data/`，重启不丢
- **电脑操控**：截屏、读屏幕文字（OCR）、读窗口控件（文字+坐标）、鼠标点击/移动/滚动、键盘输入——可视化/隐藏两种模式（`/stealth` 切换）
- **网页自动化**：Playwright 驱动，打开网页、读内容、点击、填表、截图；隐藏模式=无头后台（真·隐藏），复用系统 Edge 免下载浏览器
- **多模态看图**：`view_screen` 截屏发给 qwen2.5-vl 真正“看懂”屏幕画面（需 `ollama pull qwen2.5vl:7b`）
- **视频理解**：`video_understand` 采样关键帧序列（非逐帧）理解视频内容、动作和动态变化
- **语音输入**：`/listen` 或网页版 🎤 按钮，麦克风录音 → faster-whisper 本地转文字，直接说给它听
- **语音输出**：`/speak` 或自动朗读（`/speak_auto`），edge-tts 中文朗读回复
- **定时任务**：`/schedule 08:00 任务`，到点自动执行（如每天早汇报天气）
- **流式回复**：回复边生成边显示，不用干等
- **操作日志**：每次工具调用都记进日志，`/log` 可回看它干过什么
- **自我进化**：改自己的核心代码自动备份，可说"给你加个新能力"让它自己加工具
- **多 Agent 协作**：每个任务走「规划→执行→反思」三阶段，像规划师+执行者+审阅员协作（`/multi` 切换）
- **网页版界面**：`python webui.py` 起本地网页聊天窗口，SSE 流式实时看 agent 思考+干活，还能看记忆星球
- **安全机制**：危险命令（删除/格式化/关机等）执行前必须你按 `y` 确认；`/auto` 可切换
- **零第三方大依赖**：核心只用 Python 标准库；电脑操控用 `pyautogui` + `uiautomation` + `playwright`（各一条 pip 即可装）
- **模型自由**：默认本地 Ollama（免费、断网可用），改 3 行配置即可换任何 OpenAI 兼容 API

## 快速开始

### 环境要求

- Python 3.10+
- [Ollama](https://ollama.com)（本地跑大模型用）
- 电脑操控/网页自动化可选依赖：`pip install pyautogui uiautomation playwright`
- 多模态看图可选：`ollama pull qwen2.5vl:7b`
- 视频理解依赖：ffmpeg（自动发现，或配置 `ffmpeg_path`）+ `ollama create qwen2.5vl-16k -f Modelfile.vl`
- 语音输入依赖：`pip install faster-whisper sounddevice`（首次会下载 small 模型约 480MB，走 HF 镜像）

### 三步启动

> **懒人版**：Windows 直接双击 `安装.bat`，自动装依赖 + 检查 Ollama + 下载模型，然后双击 `启动.bat`（命令行）或 `启动网页版.bat`（网页版）即可。

```bash
# 1. 下载一个大脑（二选一，首次需要）
ollama pull qwen2.5:7b        # 快，约 4.7GB，8GB 显存全速
ollama pull qwen2.5:14b       # 更聪明，约 9GB，速度中等

# 2. 启动（Windows 双击 启动.bat）
python echo.py

# 3. 建知识库索引（可选，往 kb/ 放了 .md 文件后执行一次）
/reindex
```

> 想要网页版界面？双击 `启动网页版.bat`（或 `python webui.py`），浏览器打开 http://127.0.0.1:8899；手机连同一 WiFi 也能访问（启动时会显示局域网地址）

### 桌面版（.exe）

想要一个正经的桌面 App？打包成独立窗口程序：

```bash
pip install pyinstaller pywebview
python -m PyInstaller --onefile --name Echo桌面 desktop.py \
  --add-data "persona.md;." --add-data "config.json;." \
  --add-data "skills;skills" --add-data "kb;kb" \
  --add-data "core/ocr.ps1;core" \
  --collect-all pyautogui --collect-all uiautomation --collect-all webview \
  --collect-all edge_tts --collect-all sounddevice \
  --collect-all faster_whisper --collect-all ctranslate2 \
  --collect-all onnxruntime --collect-all playwright
```

打包后 `dist/Echo桌面.exe`（约 150MB，双击即用，独立窗口）。

然后直接说任务，例如：

```
帮我在 workspace 里写一个网页版贪吃蛇，写完自己测试
知识库里关于 RAG 的内容，总结给我
帮我联网搜一下 2026 年诺贝尔物理学奖得主是谁
记住：我每周五有英语课
```

## 项目结构

```
echo-agent/
├── echo.py          # 入口：主循环、本地指令、确认机制
├── core/
│   ├── llm.py       # 大脑：OpenAI 兼容 API 调用 + 向量化
│   ├── tools.py     # 双手：12 个工具的定义与执行（含安全检查）
│   ├── memory.py    # 记忆：事实/待办/日记/历史/提醒
│   └── rag.py       # 知识库：切块、向量化、检索
├── persona.md       # 人设：改这个文件 = 换性格，不用改代码
├── config.json      # 配置：模型、API 地址、自动确认开关
├── kb/              # 知识库：放你的 .md/.txt 知识文件
├── data/            # 运行数据（记忆、索引、历史）——不要提交到 git
└── workspace/       # 它默认的干活范围
```

## 工作原理

Agent 的心脏是 `echo.py` 里的任务循环：

```
你的目标 → 大脑思考 → 返回 tool_calls（我要用某工具）
        → 代码执行工具 → 结果喂回大脑 → 观察 → 继续或汇报
```

大模型本身碰不到你的电脑——它只能"点菜"（返回工具名+参数），
所有执行都由 `core/tools.py` 完成，危险动作有确认机制保底。

## 常用指令

| 指令 | 作用 |
|------|------|
| `/help` | 查看全部指令 |
| `/auto` | 切换危险命令自动确认（新手别开） |
| `/model qwen2.5:14b` | 热切换大脑模型 |
| `/reindex` | 重建知识库索引 |
| `/memory` / `/remember 内容` | 查看 / 添加长期记忆 |
| `/todo` / `/addtodo 内容` / `/done 编号` | 待办管理 |
| `/exit` | 退出（自动保存对话历史） |

## 换模型 / 接云端 API

编辑 `config.json`：

```jsonc
{
  "api_base": "http://localhost:11434/v1",  // Ollama 本地
  "api_key": "ollama",
  "model": "qwen2.5:7b"
}
```

接 DeepSeek 官方 API（几块钱用很久）：

```jsonc
{
  "api_base": "https://api.deepseek.com/v1",
  "api_key": "你的key",
  "model": "deepseek-chat"
}
```

代码一行不用改。

## 给它加新能力

1. 在 `core/tools.py` 的 `TOOLS` 列表照抄一个工具定义（这是给模型看的菜单）
2. 在 `_IMPL` 字典里加一行 `"工具名": 实现函数`
3. 完成。模型发现菜单上有这道菜，需要时就会点

## 安全须知

- 它能真实执行命令。危险命令有 y/n 确认，但**请自己读一遍它要做什么**
- `data/` 和 `workspace/` 含你的个人数据，开源发布时别提交（已有 .gitignore）
- 建议让它默认在 `workspace/` 里干活

## License

MIT，见 [LICENSE](LICENSE)
