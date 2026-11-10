# -*- coding: utf-8 -*-
"""webui.py —— 回声 Echo 网页版界面

启动：python webui.py   然后浏览器打开 http://127.0.0.1:8899
特点：实时看到 agent 的 规划→执行→反思 全过程（SSE 流式推送）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import agent, browser, computer, memory, tools, voice
from echo import load_config, generate_star_html

HOST, PORT = "127.0.0.1", 8899

cfg = load_config()
tools.ctx["cfg"] = cfg
tools.ctx["auto"] = cfg.get("auto_confirm", False)
tools.ctx["confirm_fn"] = lambda p: False   # 网页版无法交互确认，危险操作一律拒绝
computer.ctx["stealth"] = cfg.get("stealth", False)
browser.ctx["stealth"] = cfg.get("stealth", False)

history = memory.load_history()

PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>回声 Echo · 网页版</title>
<style>
:root{--bg:#f7f7f8;--panel:#ffffff;--border:#e6e6e8;--text:#1a1a1c;--muted:#6b6b72;--accent:#4f46e5;--accent-soft:#eef0ff;}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--text)}
#app{max-width:860px;height:100vh;margin:0 auto;display:flex;flex-direction:column;background:var(--panel)}
header{height:56px;border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;gap:10px;flex:none}
header h1{font-size:16px;margin:0;font-weight:600}
header .dot{width:8px;height:8px;border-radius:50%;background:#1d9e75}
header .sub{font-size:12px;color:var(--muted)}
#msgs{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:82%;padding:10px 14px;border-radius:14px;line-height:1.6;font-size:14px;white-space:pre-wrap;word-break:break-word}
.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
.agent{align-self:flex-start;background:var(--bg);border-bottom-left-radius:4px}
.phase{align-self:center;font-size:12px;color:var(--muted);padding:2px 10px;border-radius:10px;background:var(--accent-soft)}
.step{align-self:flex-start;font-size:12px;color:var(--muted);font-family:ui-monospace,Consolas,monospace;padding:4px 10px;background:#f0f0f2;border-radius:8px;max-width:90%}
.plan{color:#185fa5}.review{color:#993c1d}
#input{flex:none;border-top:1px solid var(--border);padding:12px;display:flex;gap:10px}
#input textarea{flex:1;height:52px;resize:none;border:1px solid var(--border);border-radius:10px;padding:10px;font-size:14px;font-family:inherit}
#input button{width:76px;border:none;border-radius:10px;background:var(--accent);color:#fff;font-size:14px;cursor:pointer}
#input button:disabled{opacity:.5;cursor:default}
</style>
</head>
<body>
<div id="app">
  <header><span class="dot"></span><h1>回声 Echo</h1><span class="sub">本地自主 Agent · 实时看它干活</span></header>
  <div id="msgs"></div>
  <div id="input">
    <textarea id="inp" placeholder="说目标，或点🎤直接说话"></textarea>
    <button id="mic" title="说话">🎤</button>
    <button id="send">发送</button>
  </div>
</div>
<script>
const msgs = document.getElementById('msgs');
const inp = document.getElementById('inp');
const send = document.getElementById('send');

function add(cls, text){
  const d = document.createElement('div');
  d.className = cls; d.textContent = text;
  msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight;
  return d;
}

async function ask(){
  const message = inp.value.trim();
  if(!message) return;
  inp.value = ''; send.disabled = true;
  add('msg user', message);
  try{
    const resp = await fetch('/chat', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message})});
    const reader = resp.body.getReader();
    const dec = new TextDecoder(); let buf = '';
    while(true){
      const {done, value} = await reader.read();
      if(done) break;
      buf += dec.decode(value, {stream:true});
      let i;
      while((i = buf.indexOf('\n\n')) >= 0){
        const chunk = buf.slice(0, i); buf = buf.slice(i+2);
        if(chunk.startsWith('data: ')){
          const ev = JSON.parse(chunk.slice(6));
          render(ev);
        }
      }
    }
  }catch(e){ add('msg agent', '连接失败：' + e); }
  send.disabled = false;
}

function render(ev){
  const t = ev.type;
  if(t === 'phase') add('phase', ev.text === '规划' ? '规划中…' : '反思中…');
  else if(t === 'plan'){ const d = add('step plan', '计划：' + ev.text); }
  else if(t === 'step') add('step', '[' + ev.step + '] ' + ev.tool + '(' + (ev.args||'').slice(0,80) + ')');
  else if(t === 'review'){ const d = add('step review', '反思：' + ev.text); }
  else if(t === 'reply') add('msg agent', ev.text);
}

send.onclick = ask;
inp.addEventListener('keydown', e => { if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); ask(); } });

const mic = document.getElementById('mic');
let rec = null, chunks = [];
mic.onclick = async () => {
  if (rec && rec.state === 'recording') { rec.stop(); mic.textContent = '🎤'; return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    rec = new MediaRecorder(stream);
    chunks = [];
    rec.ondataavailable = e => chunks.push(e.data);
    rec.onstop = async () => {
      mic.textContent = '🎤';
      add('step', '正在识别语音…');
      try {
        const blob = new Blob(chunks, {type: rec.mimeType || 'audio/webm'});
        const resp = await fetch('/listen', {method:'POST', body: blob});
        const data = await resp.json();
        if (data.text) { inp.value = data.text; add('msg agent', '我听到：「' + data.text + '」'); }
        else add('step', '没识别出内容');
      } catch(e) { add('step', '语音识别失败：' + e); }
    };
    rec.start();
    mic.textContent = '⏹';
  } catch(e) { add('step', '无法访问麦克风：' + e.message); }
};
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _sse(self, event):
        data = json.dumps(event, ensure_ascii=False)
        self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
        self.wfile.flush()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/star":
            try:
                path = generate_star_html()
                with open(path, "r", encoding="utf-8") as f:
                    body = f.read().encode("utf-8")
            except Exception as e:
                body = ("生成失败：%s" % e).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/chat":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                msg = (body.get("message") or "").strip()
            except Exception:
                msg = ""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if not msg:
                self._sse({"type": "reply", "text": "（空消息）"})
            else:
                try:
                    agent.run_agent(cfg, msg, history, self._sse)
                except Exception as e:
                    self._sse({"type": "reply", "text": "出错：%s" % e})
                memory.save_history(history)
            self._sse({"type": "done"})
        elif self.path == "/listen":
            text = ""
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = self.rfile.read(length)
                tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "data", "_voice.webm")
                os.makedirs(os.path.dirname(tmp), exist_ok=True)
                with open(tmp, "wb") as f:
                    f.write(data)
                text = voice.transcribe_file(tmp)
            except Exception as e:
                text = ""
            body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 46)
    print("  回声 Echo 网页版已启动")
    print("  浏览器打开：http://%s:%d" % (HOST, PORT))
    print("  记忆星球：  http://%s:%d/star" % (HOST, PORT))
    print("  按 Ctrl+C 退出")
    print("=" * 46)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
