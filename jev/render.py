"""终端渲染。默认带颜色，管道输出或 --no-color 时自动降级成纯文本。"""

from __future__ import annotations

import os
import sys

from .labels import DANGER_BANDS, danger_band
from .model import AnalysisResult

WIDTH = 62


class Palette:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def _wrap(self, code: str) -> str:
        return code if self.enabled else ""

    @property
    def bold(self) -> str:
        return self._wrap("\033[1m")

    @property
    def dim(self) -> str:
        return self._wrap("\033[2m")

    @property
    def red(self) -> str:
        return self._wrap("\033[31m")

    @property
    def green(self) -> str:
        return self._wrap("\033[32m")

    @property
    def yellow(self) -> str:
        return self._wrap("\033[33m")

    @property
    def cyan(self) -> str:
        return self._wrap("\033[36m")

    @property
    def magenta(self) -> str:
        return self._wrap("\033[35m")

    @property
    def reset(self) -> str:
        return self._wrap("\033[0m")

    def for_danger(self, level: float) -> str:
        if level >= 7:
            return self.red
        if level >= 4:
            return self.yellow
        return self.green


def danger_bar(level: float, palette: Palette) -> str:
    filled = max(1, min(10, int(round(float(level))) + 1))
    color = palette.for_danger(level)
    return color + "█" * filled + palette.reset + palette.dim + "░" * (10 - filled) + palette.reset


def render(result: AnalysisResult, palette: Palette | None = None, show_messages: bool = True) -> str:
    p = palette or Palette(False)
    j = result.judgment
    out: list[str] = []
    if show_messages:
        out.append("")
        out.append(p.dim + "─" * WIDTH + p.reset)
        for message in result.messages:
            tag = (p.cyan + "我" + p.reset) if message.is_me else (p.magenta + "对方" + p.reset)
            text = message.text if len(message.text) <= 46 else message.text[:46] + "…"
            out.append(f"  {tag} {text}")
        out.append(p.dim + "─" * WIDTH + p.reset)

    head = "Jev 判断" if result.backend == "jev" else "结构化判断"
    out.append(f"{p.bold}▍{head}{p.reset}  {p.dim}关系：{result.relationship}  "
               f"耗时 {result.timings.get('judge', 0):.1f}s{p.reset}")
    out.append(f"  真实意图   {p.bold}{j.intent_label}{p.reset}")
    out.append(f"  危险等级   {danger_bar(j.danger_level, p)}  "
               f"{p.for_danger(j.danger_level)}{j.danger_level:.1f}/9{p.reset}  "
               f"{p.dim}{danger_band(j.danger_level)}{p.reset}")
    out.append(f"  对方需要   {p.bold}{j.need_label}{p.reset}")
    out.append(f"  最佳动作   {p.bold}{j.action_label}{p.reset}")

    hints = []
    if j.want_substance:
        hints.append(p.green + "该给实质内容" + p.reset)
    else:
        hints.append(p.yellow + "先别给实质内容（别硬答）" + p.reset)
    hints.append((p.green + "紧张已解除" + p.reset) if j.resolved
                 else (p.red + "紧张未解除" + p.reset))
    if not j.literal:
        hints.append(p.yellow + "话里有话" + p.reset)
    out.append("  提示       " + " · ".join(hints))
    if j.reason:
        out.append(f"  {p.dim}理由       {j.reason}{p.reset}")

    if result.replies:
        out.append("")
        if result.best_index is None:
            out.append(f"{p.bold}▍候选回复{p.reset} {p.dim}(未排序){p.reset}")
        else:
            out.append(f"{p.bold}▍候选回复{p.reset} {p.dim}耗时 "
                       f"{result.timings.get('draft', 0):.1f}s + 排序 "
                       f"{result.timings.get('rank', 0):.1f}s{p.reset}")
        for i, reply in enumerate(result.replies):
            if i == result.best_index:
                out.append(f"  {p.green}✔{p.reset} {i + 1}. {p.bold}{reply}{p.reset}")
            else:
                out.append(f"    {i + 1}. {reply}")
        if result.best_index is not None:
            out.append(f"\n  {p.green}{p.bold}→ 建议发第 {result.best_index + 1} 条{p.reset}"
                       + (f"  {p.dim}{result.rank_reason}{p.reset}" if result.rank_reason else ""))

    out.append(p.dim + "─" * WIDTH + p.reset)
    out.append(f"{p.dim}发送与否、填什么，你自己定。本工具只读你贴进来的对话。{p.reset}")
    out.append("")
    return "\n".join(out)


def usage_line(result: AnalysisResult, palette: Palette | None = None) -> str:
    p = palette or Palette(False)
    usage = result.usage
    cost = f" cost={usage.cost:.6f}" if usage.cost else ""
    parts = [f"判断 {result.timings.get('judge', 0):.1f}s"]
    if "draft" in result.timings:
        parts.append(f"生成 {result.timings['draft']:.1f}s")
    if "rank" in result.timings:
        parts.append(f"排序 {result.timings['rank']:.1f}s")
    return (f"{p.dim}  tokens_in={usage.input_tokens} tokens_out={usage.output_tokens}"
            f"{cost}  ({' + '.join(parts)}){p.reset}")


def should_use_color(force_no_color: bool) -> bool:
    if force_no_color:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


__all__ = ["Palette", "render", "usage_line", "should_use_color", "danger_bar", "DANGER_BANDS"]
