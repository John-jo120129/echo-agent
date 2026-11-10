# -*- coding: utf-8 -*-
"""core/voice.py —— 语音理解（echo 的"耳朵"）

麦克风录音 → faster-whisper 本地转文字 → 交给 agent 处理。
完全本地、离线、不上传任何声音。

依赖：pip install faster-whisper sounddevice
模型：首次转写会自动下载 small 模型（约 480MB，走 HF 镜像）。
"""
import os

# 国内走 HuggingFace 镜像，加速模型下载
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def listen(seconds=5, sample_rate=16000):
    """用麦克风录音，返回 float32 numpy 数组（16kHz 单声道）。"""
    import numpy as np
    import sounddevice as sd
    audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate,
                   channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


def transcribe(audio):
    """把音频（numpy 数组）转成中文文字。"""
    import numpy as np
    # 静音检测：音量太低直接返回，避免 whisper 对静音幻觉
    if float(np.abs(np.asarray(audio)).max()) < 0.01:
        return "（没听清，请再说一遍）"
    model = _get_model()
    segments, _info = model.transcribe(audio, language="zh", beam_size=5)
    text = "".join(s.text for s in segments).strip()
    return text or "（没听清，请再说一遍）"


def transcribe_file(path):
    """把音频文件（wav/webm/mp3 等）转成中文文字。"""
    model = _get_model()
    segments, _info = model.transcribe(path, language="zh", beam_size=5)
    text = "".join(s.text for s in segments).strip()
    return text or "（没听清，请再说一遍）"


def listen_and_transcribe(seconds=5):
    """一步到位：录音 + 转文字。"""
    audio = listen(seconds)
    return transcribe(audio)


# ---------- 语音输出（说） ----------
def speak(text, voice="zh-CN-XiaoxiaoNeural"):
    """把文字用中文语音读出来（edge-tts，免费，中文自然）。"""
    import asyncio
    import tempfile
    try:
        import edge_tts
    except ImportError:
        return "还没装 edge-tts：pip install edge-tts"
    if not text or not text.strip():
        return "没有要读的内容"
    path = os.path.join(tempfile.gettempdir(), "echo_speak.mp3")

    async def _go():
        communicate = edge_tts.Communicate(text[:500], voice)
        await communicate.save(path)

    try:
        asyncio.run(_go())
    except Exception as e:
        return "语音生成失败：%s（edge-tts 需要联网）" % e
    try:
        os.startfile(path)   # 用系统默认播放器播
        return "已朗读：%s" % text[:40]
    except Exception as e:
        return "语音已生成但播放失败：%s" % e
