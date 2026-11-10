# -*- coding: utf-8 -*-
"""core/video.py —— 视频理解（动态识别）

不是"一帧一帧"单独分析，而是：均匀采样整段视频的关键帧序列，
一次性交给多模态模型，理解视频的内容、动作和动态变化。

依赖 ffmpeg（抽帧）——自动发现，找不到会给出提示。
"""
import os
import re
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME_DIR = os.path.join(BASE_DIR, "data", "_frames")

FFMPEG_CANDIDATES = [
    "ffmpeg",
    "D:/Wondershare/drfone/ffmpeg.exe",
    "C:/ffmpeg/bin/ffmpeg.exe",
]


def _ffmpeg(cfg):
    path = cfg.get("ffmpeg_path", "auto")
    if path and path != "auto" and os.path.isfile(path):
        return path
    for c in FFMPEG_CANDIDATES:
        try:
            r = subprocess.run([c, "-version"], capture_output=True, timeout=10)
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return None


def _duration(cfg, path):
    """用 ffmpeg -i 从 stderr 里解析视频时长（秒）。"""
    exe = _ffmpeg(cfg)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-i", path], capture_output=True, text=True, timeout=60)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", r.stderr)
        if m:
            h, mi, s, f = (int(m.group(i)) for i in (1, 2, 3, 4))
            return h * 3600 + mi * 60 + s + f / 100.0
    except Exception:
        pass
    return None


def video_info(cfg, path):
    exe = _ffmpeg(cfg)
    if not exe:
        return "没找到 ffmpeg。请安装后重试，或在 config.json 里配置 ffmpeg_path。"
    dur = _duration(cfg, path)
    if dur is None:
        return "读不了这个视频文件（可能不是视频，或 ffmpeg 不支持该格式）"
    r = subprocess.run([exe, "-i", path], capture_output=True, text=True, timeout=60)
    m = re.search(r"(\d{2,5})x(\d{2,5})", r.stderr)
    res = "%sx%s" % (m.group(1), m.group(2)) if m else "未知"
    return "视频时长 %.1f 秒，分辨率 %s" % (dur, res)


def video_understand(cfg, path, prompt=None, max_frames=8):
    """均匀采样关键帧序列，交给多模态模型理解视频的动态内容。"""
    from core import llm
    exe = _ffmpeg(cfg)
    if not exe:
        return "没找到 ffmpeg，无法解码视频。请安装 ffmpeg 或在 config.json 配置 ffmpeg_path。"
    if not os.path.isfile(path):
        return "视频文件不存在：%s" % path

    dur = _duration(cfg, path)
    if dur is None:
        return "读不了这个视频（可能不是视频文件）"
    fps = max_frames / max(dur, 1.0)

    os.makedirs(FRAME_DIR, exist_ok=True)
    for f in os.listdir(FRAME_DIR):
        os.remove(os.path.join(FRAME_DIR, f))

    out_pattern = os.path.join(FRAME_DIR, "f%03d.jpg")
    cmd = [exe, "-i", path, "-vf", "fps=%.4f,scale=480:-1" % fps,
           "-q:v", "4", "-frames:v", str(max_frames), out_pattern]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    frames = sorted(os.path.join(FRAME_DIR, f)
                    for f in os.listdir(FRAME_DIR) if f.endswith(".jpg"))
    if not frames:
        return "抽帧失败，可能是视频格式 ffmpeg 解不了"

    prompt = prompt or (
        "这些是按时间顺序从一段视频中均匀采样的画面帧。"
        "请基于这些帧理解并描述：1)视频的主题/内容是什么；"
        "2)发生了什么动作、事件或变化；3)明显的场景切换或动态变化。用中文。")
    try:
        return llm.call_vision(cfg, prompt, frames)
    except Exception as e:
        return "视频理解失败：%s" % e
