# -*- coding: utf-8 -*-
"""push_via_api.py — 当只有 api.github.com 可达时，用 GitHub Git Data API 同步本地提交。

逐层重建 blob / tree / commit，并校验每一步的 SHA 与本地一致；
全部一致后才 PATCH refs/heads/master（force=false，纯快进）。

用法：
    GH_TOKEN=$(gh auth token) python push_via_api.py           # 只重建+校验，不动远端分支
    GH_TOKEN=$(gh auth token) python push_via_api.py --apply   # 校验通过则更新远端分支
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.environ.get("ECHO_REPO_DIR") or os.path.dirname(os.path.abspath(__file__))
REPO = "John-jo120129/echo-agent"
BASE = "https://api.github.com/repos/" + REPO + "/git"
PROXY = (os.environ.get("ECHO_GH_PROXY") or os.environ.get("HTTPS_PROXY")
         or os.environ.get("https_proxy") or "http://127.0.0.1:60188")
TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    TOKEN = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
APPLY = "--apply" in sys.argv

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)


def api(method, path, payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=body, method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "echo-agent-api-push",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with opener.open(req, timeout=90) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError("%s %s -> HTTP %s: %s" % (
            method, path, e.code, e.read().decode("utf-8", "replace")[:600]))
    except Exception as e:
        raise RuntimeError("%s %s -> %s: %s" % (method, path, type(e).__name__, e))


def g(*args):
    return subprocess.check_output(["git"] + list(args), cwd=ROOT)


def gs(*args):
    return g(*args).decode("utf-8", "replace").strip()


def parse_ident(line):
    """b'author Name <mail> 1762943640 +0800' -> GitHub API ident dict"""
    m = re.match(r"^(.*) <(.*)> (\d+) ([+-]\d{4})$", line)
    if not m:
        raise RuntimeError("无法解析身份行: %r" % line)
    name, email, ts, tz = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    sign = 1 if tz[0] == "+" else -1
    offset = sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
    return {"name": name, "email": email,
            "date": datetime.fromtimestamp(ts, timezone(offset)).isoformat()}


def commit_meta(sha):
    """从 git cat-file commit 精确取 message / author / committer（不改字节）"""
    raw = g("cat-file", "commit", sha)
    header, sep, msg = raw.partition(b"\n\n")
    if not sep:
        raise RuntimeError("commit 头异常: " + sha)
    author = committer = None
    for line in header.split(b"\n"):
        if line.startswith(b"author "):
            author = parse_ident(line[7:].decode("utf-8"))
        elif line.startswith(b"committer "):
            committer = parse_ident(line[10:].decode("utf-8"))
    if not author or not committer:
        raise RuntimeError("缺少 author/committer: " + sha)
    return msg.decode("utf-8"), author, committer


def mode_of(rev, path, default="100644"):
    out = gs("ls-tree", rev, "--", path)
    return out.split()[0] if out else default


def main():
    print("仓库   :", ROOT)
    print("代理   :", PROXY)
    print("模式   :", "APPLY（会更新远端分支）" if APPLY else "DRY-RUN（只创建对象并校验，不动分支）")

    ref = api("GET", "/ref/heads/master")
    remote_head = ref["object"]["sha"]
    base = api("GET", "/commits/" + remote_head)
    cur_tree = base["tree"]["sha"]
    parent = remote_head
    print("远端HEAD:", remote_head[:8], "tree:", cur_tree[:8])

    commits = gs("rev-list", "--reverse", remote_head + "..HEAD").splitlines()
    if not commits:
        print("没有需要同步的提交。")
        return
    print("待同步  :", len(commits), "个提交\n")

    for i, sha in enumerate(commits, 1):
        subject = gs("show", "-s", "--format=%s", sha)
        real_parent = gs("rev-parse", sha + "^")
        if real_parent != parent:
            raise RuntimeError("父提交不连续: %s 本地父=%s 预期=%s" % (sha[:8], real_parent[:8], parent[:8]))

        msg, author, committer = commit_meta(sha)
        entries = []
        parts = g("diff-tree", "--no-commit-id", "--name-status", "-r", "-z",
                  "--no-renames", real_parent, sha).split(b"\0")
        k = 0
        while k + 1 < len(parts):
            status, path_b = parts[k], parts[k + 1]
            k += 2
            if not status or not path_b:
                continue
            path = path_b.decode("utf-8")
            st = status.decode("ascii")
            if st.startswith("D") or st.startswith("R"):
                entries.append({"path": path, "mode": mode_of(real_parent, path),
                                "type": "blob", "sha": None})
                continue
            mode = mode_of(sha, path)
            if mode == "160000":
                raise RuntimeError("遇到 submodule，API 同步不支持: " + path)
            content = g("cat-file", "blob", sha + ":" + path)
            local_blob = gs("rev-parse", sha + ":" + path)
            blob = api("POST", "/blobs", {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            })
            if blob["sha"] != local_blob:
                raise RuntimeError("blob SHA 不一致 %s: %s != %s" % (path, blob["sha"][:8], local_blob[:8]))
            entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})

        tree = api("POST", "/trees", {"base_tree": cur_tree, "tree": entries})
        local_tree = gs("rev-parse", sha + "^{tree}")
        if tree["sha"] != local_tree:
            raise RuntimeError("tree SHA 不一致 %s: %s != %s" % (sha[:8], tree["sha"][:8], local_tree[:8]))

        new = api("POST", "/commits", {
            "message": msg, "tree": tree["sha"], "parents": [parent],
            "author": author, "committer": committer,
        })
        flag = "OK " if new["sha"] == sha else "SHA变"
        print("[%d/%d] %s %s  文件=%d  %s" % (
            i, len(commits), flag, sha[:8], len(entries), subject[:46]))
        if new["sha"] != sha:
            print("      远端=%s  本地=%s（内容一致但 SHA 不同，通常是时间戳时区被规范化）"
                  % (new["sha"][:8], sha[:8]))
        cur_tree = tree["sha"]
        parent = new["sha"]

    local_head = gs("rev-parse", "HEAD")
    print("\n最终远端对象:", parent[:8], " 本地HEAD:", local_head[:8],
          " => " + ("完全一致" if parent == local_head else "SHA 不同"))

    if not APPLY:
        print("DRY-RUN 结束，未改动远端分支。加 --apply 正式更新。")
        return

    api("PATCH", "/refs/heads/master", {"sha": parent, "force": False})
    print("已更新远端 master ->", parent[:8])
    if parent == local_head:
        subprocess.check_call(["git", "update-ref", "refs/remotes/origin/master", local_head], cwd=ROOT)
        print("本地 origin/master 已对齐，git status 不再显示 ahead。")
    else:
        print("注意：SHA 不同，本地 origin/master 未改；网络恢复后 git fetch 再对齐。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\n[失败]", exc)
        sys.exit(1)
