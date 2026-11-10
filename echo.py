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

from core import agent, browser, computer, llm, memory, rag, tools

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
        "vision_model": "qwen2.5vl:7b",
        "kb_dirs": ["kb"],
        "auto_confirm": False,
        "stealth": False,
        "multi_agent": True
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
    elif cmd == "/stealth":
        cfg["stealth"] = not cfg.get("stealth", False)
        computer.ctx["stealth"] = cfg["stealth"]
        browser.ctx["stealth"] = cfg["stealth"]
        print("回声> 操控模式已切到：%s（鼠标%s，浏览器%s）" % (
            "隐藏" if cfg["stealth"] else "可视化",
            "瞬移" if cfg["stealth"] else "平滑移动",
            "无头后台" if cfg["stealth"] else "有头可见"))
    elif cmd == "/multi":
        cfg["multi_agent"] = not cfg.get("multi_agent", True)
        print("回声> 多 Agent 协作已 %s（规划→执行→反思）" % (
            "开启" if cfg["multi_agent"] else "关闭"))
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
        p = memory.load_profile()
        if p:
            print("  【档案】")
            for k, v in p.items():
                print("    · %s：%s" % (k, v))
        lt = memory.load_long_term()
        if lt:
            print("  【长期记忆】")
            for l in lt[-20:]:
                print("    · (%s) %s" % (l["date"], l["text"]))
        facts = memory.load_facts()
        if facts:
            print("  【短期记忆】")
            for f in facts[-20:]:
                print("    · (%s) %s" % (f["date"], f["text"]))
        if not p and not lt and not facts:
            print("回声> 还没有记忆，说'记住：xxx'即可")
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
    elif cmd == "/profile":
        p = memory.load_profile()
        if not p:
            print("回声> 档案还是空的。说'记住我的名字是X'即可，或 /remember_profile 键 值")
        for k, v in p.items():
            print("  · %s：%s" % (k, v))
    elif cmd == "/star":
        path = generate_star_html()
        print("回声> 记忆星球已生成：%s" % path)
        try:
            import webbrowser
            webbrowser.open("file:///" + path.replace("\\", "/"))
        except Exception:
            print("回声> 请手动用浏览器打开上面的文件")
    elif cmd == "/reset":
        memory.save_history([])
        print("回声> 对话历史已清空。")
    else:
        print("回声> 不认识这个指令，/help 看看。")
    return True


HELP_TEXT = """可用指令：
  /auto            切换危险命令自动确认（新手别开）
  /stealth         切换操控模式：可视化（平滑可见）/ 隐藏（静默瞬移）
  /model 名字      换大脑模型（如 /model qwen2.5:14b）
  /reindex         重建知识库索引（含记忆归档，改动后用）
  /star            生成并打开 3D 记忆星球（可视化所有记忆）
  /profile         查看用户档案
  /memory          查看全部记忆（档案/长期/短期）
  /time /remember /forgetall /todo /addtodo /done /reset /exit

直接说任务就行，例如：
  "读一下屏幕，看看现在有什么"
  "帮我打开记事本，输入'你好'"
  "记住我的名字是X、我喜欢Y"
  "帮我做一个好看的网页版个人主页" """


def chat(cfg):
    tools.ctx["auto"] = cfg.get("auto_confirm", False)
    tools.ctx["confirm_fn"] = confirm
    tools.ctx["cfg"] = cfg
    computer.ctx["stealth"] = cfg.get("stealth", False)
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
            summarize_and_archive(cfg, history)
            break
        if not user:
            continue

        result = local_command(user, cfg)
        if result == "EXIT":
            summarize_and_archive(cfg, history)
            break
        if result:
            memory.check_reminders()
            continue

        # 记忆类明确意图兜底（可靠写入，不赌模型自觉）
        if quick_memory(user, history):
            continue

        # ===== 多角色协作任务循环（核心逻辑在 core/agent.py）=====
        def emit(event):
            t = event["type"]
            if t == "phase":
                print("\n  【%s】" % event["text"], end=" ")
            elif t == "plan":
                print(event["text"])
            elif t == "step":
                print("  [第%d步] %s(%s)" % (event["step"], event["tool"], _brief(event["args"])))
            elif t == "review":
                print("  [反思] " + event["text"])
            elif t == "reply":
                print("\n回声> " + event["text"])

        try:
            agent.run_agent(cfg, user, history, emit)
        except Exception as e:
            print("回声> 出错了：%s" % e)
            print("       若是连不上大脑：确认 Ollama 在跑（ollama serve），"
                  "模型存在（ollama list）")
        memory.save_history(history)


def summarize_and_archive(cfg, history):
    """退出时把本次对话总结成记忆，写入 data/memories/，实现"无限上下文"。
    记忆越攒越多 = 记忆星球越"肥"，久远的记忆靠检索找回，突破上下文长度限制。"""
    if len(history) < 2:
        return
    msgs = [
        {"role": "system", "content":
         "把下面这段对话总结成 1-3 条值得长期记住的记忆，每行一条，格式「- 记忆内容」。"
         "只写记忆本身，不要写'用户说'或'助手'。若没有值得记的内容，只输出：无。"},
        {"role": "user", "content": json.dumps(history[-20:], ensure_ascii=False)}
    ]
    try:
        m = llm.call_llm(cfg, msgs, tools=[])
        text = (m.get("content") or "").strip()
    except Exception:
        return
    if not text or text == "无":
        return
    n = 0
    for line in text.splitlines():
        line = line.strip().lstrip("-·* ").strip()
        if line and len(line) > 4:
            memory.write_memory_md("会话记忆", line)
            n += 1
    if n:
        print("  [记忆星球已更新：本轮对话归档了 %d 条记忆]" % n)


STAR_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>回声 · 记忆星球</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#fbfbfc;
    font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
  #scene{position:fixed;inset:0;}
  #hud{position:fixed;top:18px;left:20px;z-index:10;pointer-events:none;}
  #hud h1{font-size:20px;margin:0 0 4px;color:#1a1a1c;font-weight:600;}
  #hud p{margin:0;font-size:13px;color:#6b6b72;}
  #legend{position:fixed;bottom:18px;left:20px;z-index:10;font-size:12px;color:#6b6b72;
    background:rgba(255,255,255,.85);padding:8px 12px;border-radius:10px;line-height:1.8;}
  #legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 6px 0 0;}
  #tooltip{position:fixed;display:none;z-index:20;max-width:320px;background:#1a1a1c;
    color:#fff;font-size:13px;padding:8px 12px;border-radius:8px;pointer-events:none;
    line-height:1.5;box-shadow:0 4px 14px rgba(0,0,0,.18);}
</style>
</head>
<body>
<div id="scene"></div>
<div id="hud"><h1>回声 · 记忆星球</h1><p>拖拽旋转 · 滚轮缩放 · 悬停看记忆</p></div>
<div id="legend">
  <i style="background:#d4a017"></i>用户档案
  <i style="background:#378add"></i>长期记忆
  <i style="background:#1d9e75"></i>短期记忆
  <i style="background:#7f77dd"></i>会话记忆
</div>
<div id="tooltip"></div>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}
</script>
<script type="module">
import * as THREE from 'three';
const DATA = __DATA__;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, innerWidth/innerHeight, 0.1, 100);
camera.position.set(0, 1.5, 6.5); camera.lookAt(0,0,0);
const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setSize(innerWidth, innerHeight);
document.getElementById('scene').appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0xffffff, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(6,6,6); scene.add(key);
const back = new THREE.DirectionalLight(0xffffff, 0.5); back.position.set(-4,-2,-4); scene.add(back);

const core = new THREE.Mesh(
  new THREE.SphereGeometry(1, 48, 48),
  new THREE.MeshPhongMaterial({color:0x4f46e5, transparent:true, opacity:0.10}));
scene.add(core);
const wire = new THREE.Mesh(
  new THREE.SphereGeometry(1, 24, 24),
  new THREE.MeshBasicMaterial({color:0x4f46e5, wireframe:true, transparent:true, opacity:0.16}));
scene.add(wire);

const group = new THREE.Group(); scene.add(group);
const colors = {0:0xd4a017, 1:0x378add, 2:0x1d9e75, 3:0x7f77dd};
const radii = {0:0.95, 1:1.35, 2:1.75, 3:2.15};
const meshes = [];

function fibonacci(n, radius){
  const out = []; const g = Math.PI*(3-Math.sqrt(5));
  for(let i=0;i<n;i++){
    const y = n>1 ? 1 - (i/(n-1))*2 : 0;
    const r = Math.sqrt(Math.max(0,1-y*y));
    const t = g*i;
    out.push([Math.cos(t)*r*radius, y*radius, Math.sin(t)*r*radius]);
  }
  return out;
}
const byLayer = {};
DATA.forEach(p => { (byLayer[p.layer] = byLayer[p.layer] || []).push(p); });
Object.keys(byLayer).forEach(layer => {
  const pos = fibonacci(byLayer[layer].length, radii[layer]);
  byLayer[layer].forEach((p, i) => {
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(0.055, 16, 16),
      new THREE.MeshPhongMaterial({color: colors[layer]}));
    m.position.set(pos[i][0], pos[i][1], pos[i][2]);
    m.userData = {text: p.text};
    group.add(m); meshes.push(m);
  });
});

let dragging = false, px = 0, py = 0;
renderer.domElement.addEventListener('pointerdown', e => {dragging=true; px=e.clientX; py=e.clientY;});
addEventListener('pointermove', e => {
  if(dragging){ group.rotation.y += (e.clientX-px)*0.005; group.rotation.x += (e.clientY-py)*0.005; px=e.clientX; py=e.clientY; }
});
addEventListener('pointerup', () => dragging=false);
addEventListener('wheel', e => {
  camera.position.z = Math.max(2.6, Math.min(12, camera.position.z + e.deltaY*0.005));
});

const raycaster = new THREE.Raycaster(), mouse = new THREE.Vector2();
const tip = document.getElementById('tooltip');
addEventListener('pointermove', e => {
  if(dragging) return;
  mouse.x = (e.clientX/innerWidth)*2-1; mouse.y = -(e.clientY/innerHeight)*2+1;
  raycaster.setFromCamera(mouse, camera);
  const hit = raycaster.intersectObjects(meshes)[0];
  if(hit){ tip.style.display='block'; tip.textContent = hit.object.userData.text;
    tip.style.left = Math.min(e.clientX+16, innerWidth-340)+'px'; tip.style.top = (e.clientY+16)+'px'; }
  else tip.style.display='none';
});
addEventListener('resize', () => { camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });

function animate(){ requestAnimationFrame(animate); if(!dragging) group.rotation.y += 0.0012; renderer.render(scene, camera); }
animate();
</script>
</body>
</html>"""


def generate_star_html():
    """把全部记忆汇总，生成一个 3D 记忆星球的 HTML 文件并返回路径。"""
    data = memory.collect_all_memories()
    points = []
    for p in data["profile"]:
        points.append({"text": "%s：%s" % (p["k"], p["v"]), "layer": 0})
    for l in data["long_term"]:
        points.append({"text": l["text"], "layer": 1, "date": l.get("date", "")})
    for f in data["facts"]:
        points.append({"text": f["text"], "layer": 2, "date": f.get("date", "")})
    for m in data["memories"]:
        points.append({"text": m["text"][:160], "layer": 3})
    if not points:
        points.append({"text": "还没有记忆，去和回声聊两句吧", "layer": 2})
    html = STAR_TEMPLATE.replace("__DATA__", json.dumps(points, ensure_ascii=False))
    path = os.path.join(BASE_DIR, "memory_star.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def quick_memory(user, history):
    """只兜底模型多轮后最不稳定的两种记忆意图；复杂句交给模型。
    命中则返回 True，否则 False。"""
    import re
    u = user.strip()
    done = None

    m = re.match(r"^(?:我的长期目标是|长期目标是|我的目标是|目标是)(.+)$", u)
    if m and len(m.group(1)) >= 2:
        done = memory.add_long_term(m.group(1).strip("的了，。 "))
    elif re.match(r"^(?:记住|帮我记|帮我记住|记一下)", u):
        content = re.sub(r"^(?:记住|帮我记|帮我记住|记一下)", "", u).strip("：:，。 ")
        if len(content) >= 2 and "岁" not in content and "我叫" not in content and "我是" not in content:
            done = memory.add_fact(content)

    if done:
        print("回声> " + done)
        history.append({"role": "assistant", "content": done})
        return True
    return False


def _brief(s, limit=80):
    s = s.replace("\n", " ")
    return s if len(s) <= limit else s[:limit] + "…"


if __name__ == "__main__":
    chat(load_config())
