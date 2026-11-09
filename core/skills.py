# -*- coding: utf-8 -*-
"""core/skills.py —— 技能体系（Agent Skills）

把一个"工作方法"打包成 skills/ 下的一个文件夹：
  skills/网页设计/
  └── SKILL.md      # 技能说明书（front matter + 正文规则）

SKILL.md 顶部用 --- 包起来的 front matter 描述：
  name         技能名
  description  干什么
  when_to_use  什么时候该用它

agent 启动时会把所有技能的摘要注入系统提示词，
遇到相关任务时调用 use_skill 加载完整规范照着做。
"""
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(BASE_DIR, "skills")


def _parse_frontmatter(text):
    """拆出 front matter 和正文。"""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2)


def _iter_skills():
    """遍历所有技能，返回 (目录名, 元信息, 正文)。"""
    result = []
    if not os.path.isdir(SKILLS_DIR):
        return result
    for d in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, d, "SKILL.md")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        meta, body = _parse_frontmatter(text)
        result.append((d, meta, body))
    return result


def list_skills():
    """技能摘要列表，注入 system prompt 用。"""
    out = []
    for d, meta, _ in _iter_skills():
        out.append({
            "name": meta.get("name", d),
            "description": meta.get("description", ""),
            "when": meta.get("when_to_use", ""),
        })
    return out


def load_skill(name):
    """按技能名（front matter name 或目录名）返回完整说明书。"""
    for d, meta, body in _iter_skills():
        if meta.get("name") == name or d == name:
            return "# 技能：%s\n\n%s" % (meta.get("name", d), body.strip())
    return "没找到技能「%s」" % name
