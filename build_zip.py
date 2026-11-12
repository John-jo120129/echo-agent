# -*- coding: utf-8 -*-
"""build_zip.py — 生成 Release 用的源码包（不含 .git / dist / 数据 / 历史包）

用法：python build_zip.py v1.4
产物：dist_zip/echo-agent-v1.4.zip，解压后是 echo-agent/ 目录。
"""
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION = sys.argv[1] if len(sys.argv) > 1 else "v1.4"
OUT = os.path.join(ROOT, "dist_zip", "echo-agent-%s.zip" % VERSION)

SKIP_PREFIX = (b"dist_zip/", b"dist/", b"build/", b"data/", b"workspace/", b".git")
SKIP_EXACT = {b".gitattributes", b".gitignore", b"test_screen.png"}


def main():
    raw = subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=ROOT)
    names = [n for n in raw.split(b"\0") if n]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in names:
            if rel.startswith(SKIP_PREFIX) or rel in SKIP_EXACT:
                continue
            path = os.path.join(ROOT, os.fsdecode(rel))
            if not os.path.isfile(path):
                continue
            z.write(path, "echo-agent/" + os.fsdecode(rel))
            count += 1
    print("生成 %s：%d 个文件，%d 字节" % (OUT, count, os.path.getsize(OUT)))
    with zipfile.ZipFile(OUT) as z:
        print("校验：%d 个条目，testzip=%s" % (len(z.namelist()), z.testzip()))
        for bat in ["echo-agent/启动.bat", "echo-agent/启动网页版.bat", "echo-agent/安装.bat"]:
            data = z.read(bat)
            ok = all(c < 128 for c in data) and data.count(b"\n") <= 1
            print("  %s -> %s (%d 字节)" % (bat, "纯ASCII单行 OK" if ok else "异常", len(data)))


if __name__ == "__main__":
    main()
