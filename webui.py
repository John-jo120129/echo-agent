# -*- coding: utf-8 -*-
"""webui.py —— 回声 Echo 网页版界面

启动：python webui.py   然后浏览器打开 http://127.0.0.1:8899
特点：实时看到 agent 的 规划→执行→反思 全过程（SSE 流式推送）。
"""
import json
import os
import sys
import socket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import agent, browser, computer, memory, tools, voice, sessionstore
from echo import load_config, generate_star_html

HOST, PORT = "0.0.0.0", 8899   # 0.0.0.0 = 局域网也能访问（手机同 WiFi 可连）

cfg = load_config()
tools.ctx["cfg"] = cfg
tools.ctx["auto"] = cfg.get("auto_confirm", False)
tools.ctx["confirm_fn"] = lambda p: False   # 网页版无法交互确认，危险操作一律拒绝
computer.ctx["stealth"] = cfg.get("stealth", False)
browser.ctx["stealth"] = cfg.get("stealth", False)

# 多会话：默认打开最近一个，没有就新建
_sess = sessionstore.ensure_default()
current_sid = _sess["id"]
history = sessionstore.load_session(current_sid)
if not history:
    # 第一次用多会话：把原来的单会话历史搬进第一个会话，不丢
    _old = memory.load_history()
    if _old:
        history = _old
        sessionstore.save_session(current_sid, history)

PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>回声 Echo · 网页版</title>
<style>
:root{--bg:#f0f1f6;--panel:#ffffff;--border:#e6e6e8;--text:#1a1a1c;--muted:#6b6b72;--accent:#4f46e5;--accent-2:#7c3aed;--accent-soft:#eef0ff;}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:linear-gradient(180deg,#e9ebff 0%,#f7f7f8 45%);font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--text)}
#app{max-width:860px;height:100vh;margin:0 auto;display:flex;flex-direction:column;background:var(--panel);box-shadow:0 0 48px rgba(79,70,229,.10)}
header{height:60px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 20px;gap:12px;flex:none;background:#fff}
.hd{display:flex;align-items:center;gap:10px}
.brand{display:flex;flex-direction:column;line-height:1.25}
.brand h1{margin:0;font-size:16px;font-weight:700;background:linear-gradient(90deg,var(--accent),var(--accent-2));-webkit-background-clip:text;background-clip:text;color:transparent}
.brand .sub{font-size:11px;color:var(--muted)}
.star{font-size:12px;color:var(--accent);text-decoration:none;padding:6px 12px;border:1px solid var(--accent-soft);border-radius:16px;transition:.2s;white-space:nowrap}
.star:hover{background:var(--accent-soft)}
.hd-right{display:flex;align-items:center;gap:8px}
#sessSel{max-width:150px;font-size:12px;padding:6px 8px;border:1px solid var(--border);border-radius:10px;background:#fff;color:var(--text);outline:none;cursor:pointer}
#sessSel:focus{border-color:var(--accent)}
#newSess{padding:6px 12px;border:1px solid var(--accent-soft);border-radius:16px;background:#fff;color:var(--accent);font-size:12px;cursor:pointer;white-space:nowrap}
#newSess:hover{background:var(--accent-soft)}
#voiceMode{padding:6px 12px;border:1px solid var(--accent-soft);border-radius:16px;background:#fff;color:var(--accent);font-size:12px;cursor:pointer;white-space:nowrap}
#voiceMode:hover{background:var(--accent-soft)}
#voiceMode.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#msgs{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:82%;padding:11px 15px;border-radius:16px;line-height:1.65;font-size:14px;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.user{align-self:flex-end;background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#fff;border-bottom-right-radius:4px}
.agent{align-self:flex-start;background:#f5f5f7;border-bottom-left-radius:4px}
.phase{align-self:center;font-size:12px;color:var(--accent);padding:3px 12px;border-radius:12px;background:var(--accent-soft)}
.step{align-self:flex-start;font-size:12px;color:var(--muted);font-family:ui-monospace,Consolas,monospace;padding:4px 10px;background:#f0f0f2;border-radius:8px;max-width:90%}
.plan{color:#185fa5}.review{color:#993c1d}
.process{align-self:flex-start;font-size:12px;margin:2px 0}
.process summary{cursor:pointer;user-select:none;color:var(--muted);padding:3px 10px;background:#f0f0f2;border-radius:8px;display:inline-block;list-style:none}
.process summary::-webkit-details-marker{display:none}
.process summary:hover{color:var(--accent)}
.process .step{margin-top:6px}
#input{flex:none;border-top:1px solid var(--border);padding:12px;display:flex;gap:10px;background:#fff}
#input textarea{flex:1;height:52px;resize:none;border:1px solid var(--border);border-radius:12px;padding:12px;font-size:14px;font-family:inherit;outline:none}
#input textarea:focus{border-color:var(--accent)}
#input button{width:76px;border:none;border-radius:12px;background:var(--accent);color:#fff;font-size:14px;cursor:pointer;transition:.15s}
#input button:hover{background:var(--accent-2)}
#input button:disabled{opacity:.5;cursor:default}
#mic{width:52px;background:#fff;color:#1a1a1c;border:1px solid var(--border)}
#mic:hover{background:var(--bg);border-color:var(--accent)}
@media(max-width:600px){.star{font-size:11px;padding:4px 8px}.brand .sub{display:none}#input button{width:64px}.msg{max-width:90%}}
</style>
</head>
<body>
<div id="app">
  <header>
    <div class="hd">
      <svg viewBox="0 0 24 24" width="22" height="22"><circle cx="12" cy="12" r="9.5" fill="none" stroke="#4f46e5" stroke-width="1.5" opacity=".25"/><circle cx="12" cy="12" r="4.5" fill="#4f46e5"/><path d="M12 2.5c1.8 2.6 1.8 4.4 0 7M12 21.5c-1.8-2.6-1.8-4.4 0-7" fill="none" stroke="#4f46e5" stroke-width="1.5" stroke-linecap="round"/></svg>
      <div class="brand"><h1>回声 Echo</h1><span class="sub">本地自主 AI Agent</span></div>
    </div>
    <div class="hd-right">
      <select id="sessSel" title="切换会话"></select>
      <button id="newSess" title="开新对话">＋ 新对话</button>
      <button id="voiceMode" title="语音模式：回复自动朗读，说话可打断">🎧 语音模式</button>
      <a class="star" href="/star" target="_blank">✦ 记忆星球</a>
    </div>
  </header>
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

let curAgent = null;
let procBox = null;
function render(ev){
  const t = ev.type;
  if(t === 'phase' || t === 'plan' || t === 'step' || t === 'review'){
    // 过程信息折叠进一个可展开块，默认收起
    if(!procBox){
      const d = document.createElement('details');
      d.className = 'process';
      const s = document.createElement('summary');
      s.textContent = '查看思考过程';
      d.appendChild(s);
      procBox = { details: d, body: document.createElement('div'), n: 0 };
      d.appendChild(procBox.body);
      msgs.appendChild(d);
    }
    const line = document.createElement('div');
    line.className = 'step';
    if(t === 'phase') line.textContent = '【' + ev.text + '】';
    else if(t === 'plan'){ line.className = 'step plan'; line.textContent = '计划：' + ev.text; }
    else if(t === 'step') line.textContent = '[' + ev.step + '] ' + ev.tool + (ev.args ? '(' + ev.args.slice(0,60) + ')' : '');
    else if(t === 'review'){ line.className = 'step review'; line.textContent = '反思：' + ev.text; }
    procBox.body.appendChild(line);
    procBox.n++;
    procBox.details.querySelector('summary').textContent = '查看思考过程（' + procBox.n + ' 步）';
    msgs.scrollTop = msgs.scrollHeight;
  }
  else if(t === 'token'){
    if(!curAgent) curAgent = add('msg agent', '');
    curAgent.textContent += ev.text;
    msgs.scrollTop = msgs.scrollHeight;
  }
  else if(t === 'reply'){
    if(procBox){ procBox = null; }
    if(curAgent){ curAgent = null; }
    else add('msg agent', ev.text);
    if (voiceMode) speakAndPlay(ev.text);
  }
}

// ---- 多会话 ----
const sessSel = document.getElementById('sessSel');
const newSessBtn = document.getElementById('newSess');

function renderHistory(list){
  msgs.innerHTML = '';
  procBox = null; curAgent = null;
  (list || []).forEach(m => {
    if (m.role === 'user') add('msg user', m.content);
    else add('msg agent', m.content);
  });
}

async function loadSessions(showMsgs){
  try{
    const d = await (await fetch('/sessions')).json();
    sessSel.innerHTML = '';
    (d.sessions || []).forEach(s => {
      const o = document.createElement('option');
      o.value = s.id;
      o.textContent = (s.title || '新对话').slice(0, 14);
      if (s.id === d.current) o.selected = true;
      sessSel.appendChild(o);
    });
    if (showMsgs) renderHistory(d.messages);
  }catch(e){}
}

sessSel.onchange = async () => {
  try{
    const d = await (await fetch('/sessions/switch', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sid: sessSel.value})})).json();
    renderHistory(d.messages);
  }catch(e){}
};

newSessBtn.onclick = async () => {
  try{
    await fetch('/sessions/new', {method:'POST'});
    renderHistory([]);
    await loadSessions(false);
  }catch(e){}
};

loadSessions(true);

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

// ---- 语音模式 + 实时打断 ----
let voiceMode = false;
let ttsAudio = null;
let vadStream = null, vadCtx = null, vadAnalyser = null, vadRaf = null, bargeCooldown = 0;
const voiceBtn = document.getElementById('voiceMode');

async function initVadMic(){
  if (!vadStream) vadStream = await navigator.mediaDevices.getUserMedia({audio:true});
  if (!vadCtx){
    vadCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = vadCtx.createMediaStreamSource(vadStream);
    vadAnalyser = vadCtx.createAnalyser();
    vadAnalyser.fftSize = 512;
    src.connect(vadAnalyser);
  }
}

function startVAD(){
  if (!vadAnalyser || vadRaf) return;
  const buf = new Uint8Array(vadAnalyser.frequencyBinCount);
  const tick = () => {
    vadAnalyser.getByteFrequencyData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i];
    const avg = sum / buf.length;
    const now = Date.now();
    // 正在播报 + 听到明显人声 → 立刻闭嘴，转为听
    if (ttsAudio && !ttsAudio.paused && avg > 35 && now > bargeCooldown){
      ttsAudio.pause();
      bargeCooldown = now + 2000;
      add('step', '（被打断）我听着，你说…');
      if (!rec || rec.state !== 'recording') mic.click();
    }
    vadRaf = requestAnimationFrame(tick);
  };
  tick();
}

function stopVAD(){ if (vadRaf){ cancelAnimationFrame(vadRaf); vadRaf = null; } }

async function speakAndPlay(text){
  if (!voiceMode || !text) return;
  try{
    const r = await fetch('/speak', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text})});
    if (!r.ok) return;
    const blob = await r.blob();
    if (ttsAudio) ttsAudio.pause();
    ttsAudio = new Audio(URL.createObjectURL(blob));
    await initVadMic();
    startVAD();
    ttsAudio.onended = () => stopVAD();
    await ttsAudio.play();
  }catch(e){}
}

voiceBtn.onclick = async () => {
  voiceMode = !voiceMode;
  voiceBtn.classList.toggle('on', voiceMode);
  voiceBtn.textContent = voiceMode ? '🎧 语音开' : '🎧 语音模式';
  if (voiceMode){
    try{
      await initVadMic();
      add('step', '语音模式已开：回复会自动朗读，你随时说话可以打断');
    }catch(e){
      add('step', '无法访问麦克风：' + e.message);
      voiceMode = false;
      voiceBtn.textContent = '🎧 语音模式';
    }
  } else {
    stopVAD();
    if (ttsAudio) ttsAudio.pause();
  }
};
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _sse(self, event):
        try:
            data = json.dumps(event, ensure_ascii=False)
            self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
            self.wfile.flush()
        except Exception:
            pass   # 客户端断开时不崩

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/sessions":
            self._json({"current": current_sid,
                        "sessions": sessionstore.list_sessions(),
                        "messages": [{"role": m.get("role"),
                                      "content": (m.get("content") or "")[:3000]}
                                     for m in history if m.get("role") in ("user", "assistant")]})
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
        global current_sid, history
        if self.path == "/sessions/new":
            rec = sessionstore.create_session()
            current_sid = rec["id"]
            history = []
            self._json({"current": current_sid, "messages": []})
            return
        if self.path == "/sessions/switch":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                sid = body.get("sid", "")
            except Exception:
                sid = ""
            if sid:
                current_sid = sid
                history = sessionstore.load_session(sid)
            self._json({"current": current_sid,
                        "messages": [{"role": m.get("role"),
                                      "content": (m.get("content") or "")[:3000]}
                                     for m in history if m.get("role") in ("user", "assistant")]})
            return
        if self.path == "/sessions/delete":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                sid = body.get("sid", "")
            except Exception:
                sid = ""
            if sid:
                sessionstore.delete_session(sid)
                if sid == current_sid:
                    rec = sessionstore.ensure_default()
                    current_sid = rec["id"]
                    history = sessionstore.load_session(current_sid)
            self._json({"current": current_sid, "sessions": sessionstore.list_sessions()})
            return
        if self.path == "/speak":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                text = body.get("text", "")
            except Exception:
                text = ""
            audio = voice.tts_bytes(text) if text else b""
            if not audio:
                self._json({"error": "语音生成失败（edge-tts 需要联网）"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
            return
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
                sessionstore.save_session(current_sid, history)
                memory.save_history(history)   # 兼容：老的单会话历史也留着
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


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    lan = _lan_ip()
    print("=" * 48)
    print("  回声 Echo 网页版已启动")
    print("  本机打开：   http://127.0.0.1:%d" % PORT)
    print("  手机/局域网：http://%s:%d  （同一 WiFi）" % (lan, PORT))
    print("  记忆星球：   http://127.0.0.1:%d/star" % PORT)
    print("  按 Ctrl+C 退出")
    print("=" * 48)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
