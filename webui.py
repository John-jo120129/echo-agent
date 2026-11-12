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
computer.ctx["stealth"] = cfg.get("stealth", False)
browser.ctx["stealth"] = cfg.get("stealth", False)

# ---------- 网页版交互：危险操作确认 + Agent 提问（都走前端弹窗） ----------
import threading
import uuid

_pending = {}                  # id -> {"ev": Event, "choice": None}
_current_emit = {"fn": None}   # 当前请求的 SSE 推送函数


def _ask_web(kind, question, options):
    """推一个 ask 事件给前端弹窗，阻塞等用户选（最长 90 秒）。"""
    emit = _current_emit.get("fn")
    if not emit:
        return None
    aid = uuid.uuid4().hex[:8]
    rec = {"ev": threading.Event(), "choice": None}
    _pending[aid] = rec
    try:
        emit({"type": "ask", "id": aid, "kind": kind,
              "question": question, "options": options})
        rec["ev"].wait(timeout=90)
        return rec["choice"]
    finally:
        _pending.pop(aid, None)


def web_confirm(prompt):
    """危险操作确认：弹窗问允许/拒绝，默认拒绝。"""
    return _ask_web("confirm", prompt, ["允许", "拒绝"]) == "允许"


def web_ask(question, options):
    """Agent 主动提问：弹出选项让用户选。"""
    c = _ask_web("question", question, options)
    return ("用户选择：%s" % c) if c else "用户没有选择（超时，请自行决定）"


tools.ctx["confirm_fn"] = web_confirm
tools.ctx["ask_fn"] = web_ask

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
body.dark{--bg:#15161a;--panel:#1e1f25;--border:#2c2e36;--text:#e6e6ea;--muted:#9a9aa3;--accent:#818cf8;--accent-2:#a78bfa;--accent-soft:#2a2d3d}
body.dark{background:linear-gradient(180deg,#1a1b22 0%,#15161a 45%)}
body.dark header,body.dark #input{background:var(--panel)}
body.dark .agent{background:#26272e}
body.dark .step,body.dark .process summary{background:#2a2b33}
body.dark #sessSel,body.dark #newSess,body.dark #delSess,body.dark #voiceMode,body.dark #mic,body.dark #imgBtn,body.dark #themeBtn{background:#1e1f25;color:var(--text)}
body.dark #input textarea{background:#15161a;color:var(--text)}
body.dark .modal{background:#1e1f25}
body.dark .modal-opts button{background:#26272e;color:var(--text)}
body.dark pre.code{background:#15161a;border-color:#2c2e36;color:#e6e6ea}
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
#delSess{padding:6px 10px;border:1px solid var(--border);border-radius:16px;background:#fff;font-size:12px;cursor:pointer}
#delSess:hover{border-color:#e5484d;color:#e5484d}
#themeBtn{padding:6px 10px;border:1px solid var(--border);border-radius:16px;background:#fff;font-size:12px;cursor:pointer}
#themeBtn:hover{border-color:var(--accent)}
#voiceMode{padding:6px 12px;border:1px solid var(--accent-soft);border-radius:16px;background:#fff;color:var(--accent);font-size:12px;cursor:pointer;white-space:nowrap}
#voiceMode:hover{background:var(--accent-soft)}
#voiceMode.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#voiceSel{font-size:12px;padding:5px 6px;border:1px solid var(--border);border-radius:10px;background:#fff;color:var(--text);display:none;outline:none;cursor:pointer}
#msgs{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:82%;padding:11px 15px;border-radius:16px;line-height:1.65;font-size:14px;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 2px rgba(0,0,0,.04);position:relative}
.copy-btn{position:absolute;top:6px;right:8px;opacity:0;border:none;background:rgba(0,0,0,.08);border-radius:6px;font-size:11px;cursor:pointer;padding:2px 6px;transition:.15s}
.user .copy-btn{background:rgba(255,255,255,.25)}
.msg:hover .copy-btn{opacity:1}
pre.code{background:#f6f8fa;border:1px solid #e5e7eb;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:12px;line-height:1.5;overflow-x:auto;margin:6px 0;white-space:pre-wrap;word-break:break-word;color:#1a1a1c}
.user{align-self:flex-end;background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#fff;border-bottom-right-radius:4px}
.agent{align-self:flex-start;background:#f5f5f7;border-bottom-left-radius:4px}
.phase{align-self:center;font-size:12px;color:var(--accent);padding:3px 12px;border-radius:12px;background:var(--accent-soft)}
.step{align-self:flex-start;font-size:12px;color:var(--muted);font-family:ui-monospace,Consolas,monospace;padding:4px 10px;background:#f0f0f2;border-radius:8px;max-width:90%}
.plan{color:#185fa5}.review{color:#993c1d}
.process{align-self:flex-start;font-size:12px;margin:2px 0}
.process summary{cursor:pointer;user-select:none;color:var(--muted);padding:3px 10px;background:#f0f0f2;border-radius:8px;display:inline-block;list-style:none}
.process summary::-webkit-details-marker{display:none}
.process summary:hover{color:var(--accent)}
.process .step{margin-top:6px;position:relative;padding-left:14px}
.process .step::before{content:'';position:absolute;left:2px;top:7px;width:6px;height:6px;border-radius:50%;background:var(--accent)}
.process .step::after{content:'';position:absolute;left:4.5px;top:16px;bottom:-7px;width:1px;background:var(--border)}
.process .step:last-child::after{display:none}
#input{flex:none;border-top:1px solid var(--border);padding:12px;display:flex;gap:10px;background:#fff}
#input textarea{flex:1;height:52px;resize:none;border:1px solid var(--border);border-radius:12px;padding:12px;font-size:14px;font-family:inherit;outline:none}
#input textarea:focus{border-color:var(--accent)}
#input button{width:76px;border:none;border-radius:12px;background:var(--accent);color:#fff;font-size:14px;cursor:pointer;transition:.15s}
#input button:hover{background:var(--accent-2)}
#input button:disabled{opacity:.5;cursor:default}
#mic{width:52px;background:#fff;color:#1a1a1c;border:1px solid var(--border)}
#mic:hover{background:var(--bg);border-color:var(--accent)}
#imgBtn{width:52px;background:#fff;color:#1a1a1c;border:1px solid var(--border)}
#imgBtn:hover{background:var(--bg);border-color:var(--accent)}
.modal-mask{position:fixed;inset:0;background:rgba(20,20,30,.45);display:none;align-items:center;justify-content:center;z-index:50;backdrop-filter:blur(4px)}
.modal-mask.show{display:flex}
.modal{background:#fff;border-radius:18px;padding:22px;max-width:440px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.25)}
.modal-title{font-size:12px;color:var(--muted);margin-bottom:8px}
.modal-q{font-size:15px;line-height:1.65;margin-bottom:16px;white-space:pre-wrap;word-break:break-word}
.modal-opts{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end}
.modal-opts button{padding:9px 16px;border:1px solid var(--border);border-radius:10px;background:#fff;font-size:14px;cursor:pointer;transition:.15s}
.modal-opts button:hover{border-color:var(--accent);color:var(--accent)}
.modal-opts button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
@media(max-width:640px){
  header{padding:0 10px;height:52px}
  .brand h1{font-size:14px}.brand .sub{display:none}
  .hd-right{gap:4px}
  #sessSel{max-width:80px;font-size:11px;padding:4px 6px}
  #newSess,#delSess,#schedBtn,#themeBtn{font-size:11px;padding:4px 7px}
  #voiceMode{font-size:11px;padding:4px 7px}
  .star{display:none}
  #msgs{padding:12px;gap:10px}
  .msg{max-width:92%;font-size:13px;padding:9px 12px}
  #input{padding:8px;gap:6px}
  #input textarea{height:44px;font-size:13px;padding:9px}
  #input button{width:auto;padding:0 10px;font-size:12px}
  #mic,#imgBtn{width:40px;padding:0}
}
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
      <button id="delSess" title="删除当前会话">🗑</button>
      <select id="voiceSel" title="音色（语音模式开启后显示）">
        <option value="zh-CN-XiaoxiaoNeural">晓晓（女）</option>
        <option value="zh-CN-YunxiNeural">云希（男）</option>
        <option value="zh-CN-XiaoyiNeural">晓伊（女·可爱）</option>
        <option value="zh-CN-YunyangNeural">云扬（男·播音）</option>
        <option value="zh-CN-liaoning-XiaobeiNeural">晓北（东北话）</option>
        <option value="zh-CN-shaanxi-XiaoniNeural">晓妮（陕西话）</option>
      </select>
      <button id="voiceMode" title="语音模式：回复自动朗读，说话可打断">🎧 语音模式</button>
      <button id="schedBtn" title="定时任务">⏰</button>
      <button id="themeBtn" title="深色/浅色">🌙</button>
      <a class="star" href="/star" target="_blank">✦ 记忆星球</a>
    </div>
  </header>
  <div id="msgs"></div>
  <div id="input">
    <textarea id="inp" placeholder="说目标，或点🎤直接说话"></textarea>
    <button id="imgBtn" title="发图片给它看">📷</button>
    <input type="file" id="fileInput" accept="image/*" style="display:none">
    <button id="mic" title="说话">🎤</button>
    <button id="send">发送</button>
  </div>
</div>
<div id="modal" class="modal-mask">
  <div class="modal">
    <div class="modal-title" id="mTitle">需要你确认</div>
    <div class="modal-q" id="mQ"></div>
    <div class="modal-opts" id="mOpts"></div>
  </div>
</div>
<div id="schedModal" class="modal-mask">
  <div class="modal">
    <div class="modal-title">定时任务（每天到点自动执行）</div>
    <div id="schedList" style="margin:10px 0 14px;max-height:220px;overflow-y:auto"></div>
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <input id="schedTime" placeholder="08:00" style="width:76px;padding:8px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text)">
      <input id="schedTask" placeholder="任务内容（如：汇报今日天气）" style="flex:1;padding:8px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text)">
    </div>
    <div class="modal-opts">
      <button class="primary" onclick="addSchedule()">添加</button>
      <button onclick="document.getElementById('schedModal').classList.remove('show')">关闭</button>
    </div>
  </div>
</div>
<script>
const msgs = document.getElementById('msgs');
const inp = document.getElementById('inp');
const send = document.getElementById('send');

function add(cls, text){
  const d = document.createElement('div');
  d.className = cls;
  const isMsg = cls.indexOf('msg') >= 0;
  if (isMsg && text && text.indexOf('```') >= 0){
    // 简单代码块渲染（``` 围栏）
    text.split('```').forEach((p, i) => {
      if (i % 2 === 1){
        const pre = document.createElement('pre');
        pre.className = 'code';
        pre.textContent = p.replace(/^[a-zA-Z0-9_+-]*\n/, '');
        d.appendChild(pre);
      } else if (p){
        const sp = document.createElement('span');
        sp.textContent = p;
        d.appendChild(sp);
      }
    });
  } else {
    d.textContent = text;
  }
  if (isMsg){
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = '📋'; btn.title = '复制';
    btn.onclick = (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(text || '').then(() => {
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = '📋'; }, 1200);
      }).catch(() => {});
    };
    d.appendChild(btn);
  }
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
  else if(t === 'ask'){ showAsk(ev); }
}

// ---- 弹窗：危险操作确认 / Agent 提问 ----
const modal = document.getElementById('modal');
const mTitle = document.getElementById('mTitle');
const mQ = document.getElementById('mQ');
const mOpts = document.getElementById('mOpts');
let modalTimer = null;

function showAsk(ev){
  mTitle.textContent = ev.kind === 'confirm' ? '需要你确认' : '它想问你';
  mQ.textContent = ev.question || '';
  mOpts.innerHTML = '';
  (ev.options && ev.options.length ? ev.options : ['确定']).forEach((opt, i) => {
    const b = document.createElement('button');
    b.textContent = opt;
    if (i === 0) b.className = 'primary';
    b.onclick = () => answerAsk(ev.id, opt);
    mOpts.appendChild(b);
  });
  modal.classList.add('show');
  // 90 秒没人点就自动收起（后端也会超时）
  clearTimeout(modalTimer);
  modalTimer = setTimeout(() => modal.classList.remove('show'), 90000);
}

async function answerAsk(id, choice){
  modal.classList.remove('show');
  try{
    await fetch('/answer', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id, choice})});
  }catch(e){}
}

// ---- 图片上传：发图给它看 ----
const imgBtn = document.getElementById('imgBtn');
const fileInput = document.getElementById('fileInput');
imgBtn.onclick = () => fileInput.click();
fileInput.onchange = async () => {
  const f = fileInput.files && fileInput.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = async () => {
    const dataUrl = reader.result;
    add('msg user', '📷 [图片] ' + f.name);
    const d = add('msg agent', '正在看图…');
    try{
      const r = await fetch('/chat', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({message: '看看这张图片，说说里面有什么', image: dataUrl})});
      const txt = await r.text();
      // 简单处理：直接把 SSE 里的 reply 提取出来
      let out = '';
      txt.split('\n\n').forEach(ch => {
        if (ch.startsWith('data: ')){
          try{
            const ev = JSON.parse(ch.slice(6));
            if (ev.type === 'reply') out = ev.text;
          }catch(e){}
        }
      });
      d.textContent = out || '（没看懂这张图）';
    }catch(e){ d.textContent = '图片分析失败：' + e; }
  };
  reader.readAsDataURL(f);
  fileInput.value = '';
};

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

const delSessBtn = document.getElementById('delSess');
delSessBtn.onclick = async () => {
  if (!sessSel.value) return;
  if (!window.confirm('删除当前会话？删除后不可恢复')) return;
  try{
    await fetch('/sessions/delete', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sid: sessSel.value})});
    renderHistory([]);
    await loadSessions(true);
  }catch(e){}
};

loadSessions(true);

// ---- 深色模式 ----
const themeBtn = document.getElementById('themeBtn');
function applyTheme(dark){
  document.body.classList.toggle('dark', dark);
  themeBtn.textContent = dark ? '☀️' : '🌙';
  try{ localStorage.setItem('echo_theme', dark ? 'dark' : 'light'); }catch(e){}
}
themeBtn.onclick = () => applyTheme(!document.body.classList.contains('dark'));
applyTheme(localStorage.getItem('echo_theme') === 'dark');

// ---- 记住音色选择 ----
const voiceSelEl = document.getElementById('voiceSel');
try{
  const sv = localStorage.getItem('echo_voice');
  if (sv) voiceSelEl.value = sv;
}catch(e){}
voiceSelEl.onchange = () => {
  try{ localStorage.setItem('echo_voice', voiceSelEl.value); }catch(e){}
};

// ---- 定时任务 ----
const schedBtn = document.getElementById('schedBtn');
const schedModal = document.getElementById('schedModal');
const schedList = document.getElementById('schedList');

async function loadSchedule(){
  try{
    const d = await (await fetch('/schedule')).json();
    schedList.innerHTML = '';
    if (!d.items || !d.items.length){
      const e = document.createElement('div');
      e.style.cssText = 'color:var(--muted);font-size:13px';
      e.textContent = '还没有定时任务';
      schedList.appendChild(e);
      return;
    }
    (d.items || []).forEach((s, i) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px;gap:10px';
      const span = document.createElement('span');
      span.style.cssText = 'flex:1;word-break:break-all';
      span.textContent = s.time + ' · ' + s.task;
      const del = document.createElement('button');
      del.textContent = '删';
      del.style.cssText = 'border:none;background:none;color:#e5484d;cursor:pointer;font-size:12px;flex:none';
      del.onclick = async () => {
        try{
          await fetch('/schedule/delete', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({index: i})});
          loadSchedule();
        }catch(e){}
      };
      row.appendChild(span); row.appendChild(del);
      schedList.appendChild(row);
    });
  }catch(e){}
}

async function addSchedule(){
  const time = document.getElementById('schedTime').value.trim();
  const task = document.getElementById('schedTask').value.trim();
  if (!time || !task) return;
  try{
    await fetch('/schedule/add', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({time, task})});
    document.getElementById('schedTask').value = '';
    loadSchedule();
  }catch(e){}
}

schedBtn.onclick = () => { loadSchedule(); schedModal.classList.add('show'); };

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
      stopRecVAD();
      add('step', '正在识别语音…');
      try {
        const blob = new Blob(chunks, {type: rec.mimeType || 'audio/webm'});
        const resp = await fetch('/listen', {method:'POST', body: blob});
        const data = await resp.json();
        if (data.text) {
          add('msg agent', '我听到：「' + data.text + '」');
          inp.value = data.text;
          if (voiceMode) ask();   // 语音模式：说完直接发，不用再点
        }
        else add('step', '没识别出内容');
      } catch(e) { add('step', '语音识别失败：' + e); }
    };
    rec.start();
    mic.textContent = '⏹';
    // 语音模式下：静音 900ms 自动结束录音（不用手动点停止）
    if (voiceMode) {
      try { await initVadMic(); } catch(e){}
      startRecVAD();
    }
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

// 录音时的静音检测：说完了（静音 900ms）自动停止
let recVadTimer = null;
function startRecVAD(){
  if (!vadAnalyser || recVadTimer) return;
  const buf = new Uint8Array(vadAnalyser.frequencyBinCount);
  let silence = 0;
  recVadTimer = setInterval(() => {
    if (!rec || rec.state !== 'recording') { stopRecVAD(); return; }
    vadAnalyser.getByteFrequencyData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i];
    const avg = sum / buf.length;
    if (avg < 12) {
      silence += 100;
      if (silence >= 900){ stopRecVAD(); if (rec.state === 'recording') rec.stop(); }
    } else {
      silence = 0;
    }
  }, 100);
}
function stopRecVAD(){ if (recVadTimer){ clearInterval(recVadTimer); recVadTimer = null; } }

async function speakAndPlay(text){
  if (!voiceMode || !text) return;
  try{
    const vs = document.getElementById('voiceSel');
    const r = await fetch('/speak', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text, voice: vs ? vs.value : ''})});
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
  const vs = document.getElementById('voiceSel');
  if (vs) vs.style.display = voiceMode ? 'block' : 'none';
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


def _describe_image(cfg, data_url):
    """把前端上传的 base64 图片交给视觉模型看，返回中文描述。"""
    try:
        import base64
        b64 = data_url.split(",")[-1]
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "_upload.png")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(base64.b64decode(b64))
        from core import llm
        return llm.call_vision(cfg, "用中文简要描述这张图：里面有什么、在做什么、有没有文字。", [tmp])
    except Exception:
        return ""


def _scheduler_thread():
    """网页版定时任务线程：到点自动执行，结果追加进当前会话。"""
    import datetime as _dt
    import time as _time
    while True:
        try:
            now = _dt.datetime.now()
            hm = now.strftime("%H:%M")
            today = now.strftime("%Y-%m-%d")
            items = memory.load_schedule()
            changed = False
            for s in items:
                if s.get("time") == hm and s.get("last_run") != today:
                    try:
                        agent.run_agent(cfg, s.get("task", ""), history, lambda e: None)
                    except Exception:
                        pass
                    s["last_run"] = today
                    changed = True
            if changed:
                memory.save_schedule(items)
                sessionstore.save_session(current_sid, history)
        except Exception:
            pass
        _time.sleep(30)


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
        elif self.path == "/schedule":
            self._json({"items": memory.load_schedule()})
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
        if self.path == "/schedule/add":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                t = (body.get("time") or "").strip()
                task = (body.get("task") or "").strip()
            except Exception:
                t, task = "", ""
            if t and task:
                memory.add_schedule(t, task)
            self._json({"items": memory.load_schedule()})
            return
        if self.path == "/schedule/delete":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                idx = body.get("index")
            except Exception:
                idx = None
            items = memory.load_schedule()
            if isinstance(idx, int) and 0 <= idx < len(items):
                items.pop(idx)
                memory.save_schedule(items)
            self._json({"items": memory.load_schedule()})
            return
        if self.path == "/answer":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                aid = body.get("id")
                choice = body.get("choice")
            except Exception:
                aid, choice = None, None
            rec = _pending.get(aid) if aid else None
            if rec:
                rec["choice"] = choice
                rec["ev"].set()
            self._json({"ok": bool(rec)})
            return
        if self.path == "/speak":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                text = body.get("text", "")
                vname = body.get("voice") or "zh-CN-XiaoxiaoNeural"
            except Exception:
                text, vname = "", "zh-CN-XiaoxiaoNeural"
            audio = voice.tts_bytes(text, vname) if text else b""
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
            img = ""
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                msg = (body.get("message") or "").strip()
                img = body.get("image") or ""
            except Exception:
                msg = ""
            if img:
                desc = _describe_image(cfg, img)
                if desc:
                    msg = "【用户发来一张图片，视觉模型看到的内容：%s】\n%s" % (desc, msg)
                else:
                    msg = "（用户发来一张图片，但视觉模型没识别出内容，可以先说明没看到图）\n" + msg
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if not msg:
                self._sse({"type": "reply", "text": "（空消息）"})
            else:
                try:
                    _current_emit["fn"] = self._sse
                    agent.run_agent(cfg, msg, history, self._sse)
                except Exception as e:
                    self._sse({"type": "reply", "text": "出错：%s" % e})
                finally:
                    _current_emit["fn"] = None
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
    threading.Thread(target=_scheduler_thread, daemon=True).start()   # 定时任务
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
