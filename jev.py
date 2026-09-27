#!/usr/bin/env python3
"""兼容入口：早期版本是单文件脚本，现在代码在 jev/ 包里，这里只做转发。

用法和以前一样：python3 jev.py <chat.txt> / python3 jev.py（交互）
推荐用仓库自带的启动器：./bin/jev（会自动挑 Python 3.9+）。
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if sys.version_info < (3, 9):
    import shutil

    for candidate in ("python3.12", "python3.11"):
        exe = shutil.which(candidate) or os.path.expanduser(f"~/.local/bin/{candidate}")
        if os.path.exists(exe):
            os.execv(exe, [exe, os.path.abspath(__file__), *sys.argv[1:]])
    sys.exit(f"需要 Python 3.9+，当前 {sys.version.split()[0]}")

runpy.run_module("jev", run_name="__main__")
