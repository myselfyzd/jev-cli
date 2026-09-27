"""剪贴板：有就用，没有就老实说不支持（不装依赖）。"""

from __future__ import annotations

import shutil
import subprocess

WRITE_COMMANDS = (
    ("xclip", ["xclip", "-selection", "clipboard"]),
    ("xsel", ["xsel", "--clipboard", "--input"]),
    ("wl-copy", ["wl-copy"]),
    ("pbcopy", ["pbcopy"]),
    ("clip.exe", ["clip.exe"]),
)
READ_COMMANDS = (
    ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
    ("xsel", ["xsel", "--clipboard", "--output"]),
    ("wl-paste", ["wl-paste"]),
    ("pbpaste", ["pbpaste"]),
    ("powershell.exe", ["powershell.exe", "-command", "Get-Clipboard"]),
)


def _run(command: list[str], text: str | None = None) -> str | None:
    try:
        completed = subprocess.run(command, input=text, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout if text is None else ""


def available_tool() -> str | None:
    for name, _ in WRITE_COMMANDS:
        if shutil.which(name):
            return name
    return None


def copy_to_clipboard(text: str) -> str | None:
    for name, command in WRITE_COMMANDS:
        if shutil.which(name) and _run(command, text) is not None:
            return name
    return None


def read_clipboard() -> str | None:
    for name, command in READ_COMMANDS:
        if shutil.which(name):
            out = _run(command)
            if out:
                return out
    return None


__all__ = ["copy_to_clipboard", "read_clipboard", "available_tool"]
