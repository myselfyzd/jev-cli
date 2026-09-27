"""命令行入口：交互模式 + analyze / calibrate / config / logs / show 子命令。

    jev                          交互模式（stdin 不是终端时读管道）
    jev analyze chat.txt         单次分析
    jev calibrate --limit 5      在标注集上跑 judge，出命中率/误差表
    jev config show              看配置和 key 状态
    jev logs -n 10               看历史分析
    jev show latest              回看某次分析
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .backends import build_judge, build_ranker, build_writer
from .calibrate import load_cases, render_table, run_cases, summarize, write_report
from .clipboard import copy_to_clipboard, read_clipboard
from .config import (CONFIG_PATH, PROJECT_DIR, Config, load_config,
                     resolve_deepseek_key, resolve_openrouter_key, save_config)
from .input_parser import format_transcript, parse_block
from .llm import LLMError
from .model import AnalysisResult, Judgment, Message, Usage
from .pipeline import analyze
from .questions import MAX_MESSAGES
from .render import Palette, render, should_use_color, usage_line
from .store import list_records, read_record, save_record

INTERACTIVE_HELP = """命令：
  /go              分析当前这段对话（直接回车也行）
  /rel <关系>      改关系描述（会影响判断结果，比如「情侣」「同事」「客户经理」）
  /list            列出当前缓冲的消息
  /del             删掉最后一条
  /clear           清空缓冲
  /paste           把剪贴板内容追加进缓冲
  /copy [N]       把第 N 条候选复制到剪贴板（默认复制排序第一那条）
  /json            打印上一次分析的 JSON
  /help            看这份帮助
  /q               退出
输入：一行一条消息，写「对方: xxx」或「我: xxx」；不带前缀按对方算。"""


# ---------------------------------------------------------------- 参数

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jev", add_help=True,
        description="聊天回复决策辅助：judge 结构化判断 -> 生成 3 条候选 -> judge 排序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  jev -r 情侣                     交互模式\n"
               "  jev analyze chat.txt            分析一个文件\n"
               "  cat chat.txt | jev              从管道读\n"
               "  jev calibrate --limit 5         先跑 5 条看校准对不对\n"
               "  jev -j jev -r 情侣              判断层换成 TypeSafe Jev\n")
    parser.add_argument("command", nargs="?", default=None,
                        help="analyze | calibrate | config | logs | show（默认交互/管道）")
    parser.add_argument("args", nargs="*", help="子命令参数（文件路径等）")
    parser.add_argument("-r", "--relationship", help="关系描述，喂给判断模型")
    parser.add_argument("-j", "--judge", choices=("deepseek", "jev"),
                        help="判断后端；jev 需要 OPENROUTER_API_KEY")
    parser.add_argument("-m", "--model", help="模型名（默认 deepseek-chat）")
    parser.add_argument("--no-rank", action="store_true", help="生成后不让 judge 排序")
    parser.add_argument("--judge-only", action="store_true", help="只出判断，不生成候选")
    parser.add_argument("--json", action="store_true", help="只输出 JSON 到 stdout")
    parser.add_argument("--no-color", action="store_true", help="不要颜色")
    parser.add_argument("--quiet", action="store_true", help="不打印 token/耗时行")
    parser.add_argument("--clip", action="store_true", help="从剪贴板读对话")
    parser.add_argument("--limit", type=int, help="calibrate：只跑前 N 条")
    parser.add_argument("--sleep", type=float, help="calibrate：每条之间的间隔秒数")
    parser.add_argument("--out", help="calibrate：报告输出目录")
    parser.add_argument("--fixtures", help="校准标注集路径")
    parser.add_argument("-n", type=int, default=10, help="logs：显示条数")
    parser.add_argument("--version", action="version", version=f"jev-cli {__version__}")
    return parser


def apply_overrides(cfg: Config, args) -> Config:
    if args.relationship:
        cfg.relationship = args.relationship
    if args.judge:
        cfg.judge = args.judge
    if args.model:
        cfg.model = args.model
    if args.no_rank:
        cfg.rank = False
    if args.quiet:
        cfg.quiet = True
    if args.no_color:
        cfg.color = False
    if args.fixtures:
        cfg.fixtures = args.fixtures
    return cfg


def make_engines(cfg: Config, judge_only: bool):
    """按配置组装 (judge, writer, ranker)。缺哪个 key 就报哪个 key 的错。"""
    deepseek_key = resolve_deepseek_key(cfg)
    openrouter_key = resolve_openrouter_key(cfg)
    judge = build_judge(cfg.judge, cfg.model, deepseek_key, openrouter_key)
    if judge_only:
        return judge, None, None
    writer = build_writer(deepseek_key, cfg.model)
    ranker = build_ranker(cfg.judge, cfg.model, deepseek_key, openrouter_key) if cfg.rank else None
    return judge, writer, ranker


# ---------------------------------------------------------------- 输出

def emit(result: AnalysisResult, cfg: Config, palette: Palette, *, as_json: bool = False,
         show_messages: bool = True) -> None:
    if as_json:
        print(json.dumps(result.to_record(time.strftime("%Y-%m-%d %H:%M:%S")),
                         ensure_ascii=False, indent=2))
        return
    print(render(result, palette, show_messages=show_messages))
    if not cfg.quiet:
        print(usage_line(result, palette))


def save_and_hint(result: AnalysisResult, cfg: Config, palette: Palette) -> Path:
    path = save_record(result, Path(cfg.log_dir))
    if not cfg.quiet:
        print(f"{palette.dim}  记录已存 {path}{palette.reset}\n")
    return path


# ---------------------------------------------------------------- 子命令

def cmd_analyze(args, cfg: Config) -> int:
    texts: list[str] = []
    if args.args:
        for target in args.args:
            path = Path(target)
            if not path.exists():
                print(f"找不到文件：{target}", file=sys.stderr)
                return 2
            texts.append(path.read_text(encoding="utf-8"))
    elif args.clip:
        clip = read_clipboard()
        if not clip:
            print("读不到剪贴板（没装 xclip/xsel/wl-paste？）", file=sys.stderr)
            return 2
        texts.append(clip)
    elif not sys.stdin.isatty():
        texts.append(sys.stdin.read())
    else:
        print("没有输入：给个文件路径、用管道，或者在交互模式下按 /go", file=sys.stderr)
        return 2

    messages: list[Message] = []
    for text in texts:
        messages.extend(parse_block(text, limit=0))
    messages = messages[-MAX_MESSAGES:]
    if not messages:
        print("没解析出消息", file=sys.stderr)
        return 2
    if messages[-1].is_me:
        print("提示：最后一条是你自己发的，判断会偏（原项目只分析对方发来的消息）", file=sys.stderr)

    palette = Palette(should_use_color(args.no_color) and cfg.color)
    try:
        judge, writer, ranker = make_engines(cfg, args.judge_only)
        result = analyze(messages, cfg.relationship, judge, writer=writer, ranker=ranker,
                         do_rank=cfg.rank, judge_only=args.judge_only)
    except LLMError as exc:
        print(f"出错了：{exc}", file=sys.stderr)
        return 2
    emit(result, cfg, palette, as_json=args.json)
    save_and_hint(result, cfg, palette)
    return 0


def cmd_calibrate(args, cfg: Config) -> int:
    fixtures = Path(cfg.fixtures)
    if not fixtures.exists():
        print(f"找不到标注集：{fixtures}", file=sys.stderr)
        return 2
    cases = load_cases(fixtures)
    palette = Palette(should_use_color(args.no_color) and cfg.color)
    out_dir = Path(args.out) if args.out else PROJECT_DIR / "report"
    sleep = args.sleep if args.sleep is not None else None

    try:
        judge = build_judge(cfg.judge, cfg.model, resolve_deepseek_key(cfg),
                           resolve_openrouter_key(cfg))
    except LLMError as exc:
        print(f"出错了：{exc}", file=sys.stderr)
        return 2

    def progress(index: int, total: int, row: dict) -> None:
        if row.get("ok"):
            predicted = row["predicted"]
            print(f"[{index}/{total}] {row['id']} ok  intent={predicted.get('true_intent')} "
                  f"danger={predicted.get('danger_level'):.1f} "
                  f"needs={predicted.get('she_needs')} "
                  f"hit={sum(1 for v in row['hit'].values() if v is True)}/"
                  f"{sum(1 for v in row['hit'].values() if v is not None)}", flush=True)
        else:
            print(f"[{index}/{total}] {row['id']} 失败：{row.get('error')}", flush=True)

    kwargs = {"limit": args.limit, "on_row": progress}
    if sleep is not None:
        kwargs["sleep"] = sleep
    rows = run_cases(cases, judge, **kwargs)
    summary = summarize(rows)
    print()
    print(render_table(summary))
    json_path, md_path = write_report(out_dir, summary, rows, judge=cfg.judge, fixtures=fixtures)
    print(f"\n报告：{json_path}\n      {md_path}")

    if summary["n_errors"]:
        return 1
    if not all(summary["gates"].values()):
        return 2
    return 0


def cmd_config(args, cfg: Config) -> int:
    action = args.args[0] if args.args else "show"
    if action in ("show", "list"):
        deepseek_key = resolve_deepseek_key(cfg)
        openrouter_key = resolve_openrouter_key(cfg)
        rows = [
            ("配置文件", f"{CONFIG_PATH}{'' if CONFIG_PATH.exists() else '（还没创建，jev config init 生成）'}"),
            ("关系描述", cfg.relationship),
            ("judge", cfg.judge),
            ("模型", cfg.model),
            ("排序", "开" if cfg.rank else "关"),
            ("记录目录", cfg.log_dir),
            ("标注集", cfg.fixtures),
            ("DEEPSEEK", f"已找到（{deepseek_key[:6]}…{deepseek_key[-4:]}）" if deepseek_key else "缺失"),
            ("OPENROUTER", f"已找到（{openrouter_key[:6]}…{openrouter_key[-4:]}）" if openrouter_key
             else "缺失（judge=jev 才需要）"),
        ]
        for name, value in rows:
            print(f"{name:<10} {value}")
        return 0
    if action == "init":
        path = save_config(cfg)
        print(f"已写入 {path}")
        return 0
    if action == "path":
        print(CONFIG_PATH)
        return 0
    if action == "set":
        if len(args.args) < 3:
            print("用法：jev config set <字段> <值>", file=sys.stderr)
            print("字段：relationship / judge / model / rank / color / quiet / log_dir / fixtures",
                  file=sys.stderr)
            return 2
        field, value = args.args[1], " ".join(args.args[2:])
        if not hasattr(cfg, field):
            print(f"没有这个字段：{field}", file=sys.stderr)
            return 2
        current = getattr(cfg, field)
        if isinstance(current, bool):
            value = value.strip().lower() in ("1", "true", "on", "yes", "开", "是")
        setattr(cfg, field, value)
        path = save_config(cfg)
        print(f"{field} = {getattr(cfg, field)}  ->  {path}")
        return 0
    print(f"不认识的 config 动作：{action}（可选 show / init / path / set）", file=sys.stderr)
    return 2


def cmd_logs(args, cfg: Config) -> int:
    rows = list_records(Path(cfg.log_dir), limit=args.n)
    if not rows:
        print(f"{cfg.log_dir} 里还没有记录")
        return 0
    print(f"{'#':>3}  {'时间':<19} {'判断':<8} {'意图':<12} {'危险':>5}  {'首选':>4}  最后一条")
    print("-" * 84)
    for index, row in enumerate(rows, start=1):
        best = "-" if row["best_index"] is None else str(row["best_index"] + 1)
        print(f"{index:>3}  {row['ts']:<19} {row['backend']:<8} {row['intent']:<12} "
              f"{row['danger']:>5.1f}  {best:>4}  {row['preview']}")
    print(f"\n回看：jev show {rows[0]['path']}")
    return 0


def record_to_result(data: dict) -> AnalysisResult:
    result = AnalysisResult(
        messages=[Message(m["from"], m["text"]) for m in data.get("messages", [])],
        relationship=data.get("relationship", ""),
        judgment=Judgment.from_dict(data.get("judgment") or {}),
        replies=list(data.get("replies") or []),
        best_index=data.get("best_index"),
        rank_reason=data.get("rank_reason", ""),
        backend=data.get("backend", ""),
    )
    result.timings = dict(data.get("timings") or {})
    usage = data.get("usage") or {}
    result.usage = Usage(int(usage.get("input_tokens") or 0),
                         int(usage.get("output_tokens") or 0),
                         float(usage.get("cost") or 0))
    return result


def cmd_show(args, cfg: Config) -> int:
    if not args.args:
        print("用法：jev show <记录路径|latest>", file=sys.stderr)
        return 2
    target = args.args[0]
    if target == "latest":
        rows = list_records(Path(cfg.log_dir), limit=1)
        if not rows:
            print("没有记录", file=sys.stderr)
            return 2
        path = rows[0]["path"]
    else:
        path = Path(target)
    if not Path(path).exists():
        print(f"找不到记录：{path}", file=sys.stderr)
        return 2
    data = read_record(Path(path))
    palette = Palette(should_use_color(args.no_color) and cfg.color)
    result = record_to_result(data)
    print(render(result, palette))
    print(f"{palette.dim}  {path}{palette.reset}\n")
    return 0


# ---------------------------------------------------------------- 交互模式

def interactive(args, cfg: Config) -> int:
    palette = Palette(should_use_color(args.no_color) and cfg.color)
    try:
        engines = make_engines(cfg, args.judge_only)
    except LLMError as exc:
        print(f"{palette.red}出错了：{exc}{palette.reset}", file=sys.stderr)
        print("设好 key 再进来：export DEEPSEEK_API_KEY=sk-...\n"
              "（本机也可以直接用 ~/chat_tool/config.json 里已有的 key）", file=sys.stderr)
        return 2
    judge, writer, ranker = engines

    print(f"{palette.bold}jev-cli {__version__}{palette.reset} "
          f"{palette.dim}judge={cfg.judge} 关系={cfg.relationship} 最多带 {MAX_MESSAGES} 条{palette.reset}")
    print(f"{palette.dim}输入 /help 看命令；一行一条消息，/go 开始分析。{palette.reset}\n")

    messages: list[Message] = []
    last: AnalysisResult | None = None
    while True:
        try:
            line = input(f"{palette.dim}[{len(messages)}]{palette.reset} > ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        command, _, rest = line.partition(" ")
        command = command.strip().lower()

        if command in ("/q", "/quit", "/exit"):
            return 0
        if command in ("/help", "/h", "/?"):
            print(INTERACTIVE_HELP)
            continue
        if command == "/rel":
            if rest.strip():
                cfg.relationship = rest.strip()
                save_config(cfg)
            print(f"{palette.dim}关系 = {cfg.relationship}{palette.reset}")
            continue
        if command == "/list":
            if not messages:
                print(f"{palette.dim}（空）{palette.reset}")
            for index, message in enumerate(messages):
                tag = "我" if message.is_me else "对方"
                print(f"  {index}: {tag}: {message.text}")
            continue
        if command == "/del":
            if messages:
                removed = messages.pop()
                print(f"{palette.dim}删掉：{removed.text}{palette.reset}")
            continue
        if command == "/clear":
            messages.clear()
            last = None
            print(f"{palette.dim}已清空{palette.reset}")
            continue
        if command == "/paste":
            clip = read_clipboard()
            if not clip:
                print(f"{palette.yellow}读不到剪贴板{palette.reset}")
                continue
            added = parse_block(clip, limit=0)
            messages.extend(added)
            messages = messages[-MAX_MESSAGES:]
            print(f"{palette.dim}从剪贴板加了 {len(added)} 条{palette.reset}")
            continue
        if command == "/copy":
            if last is None or not last.replies:
                print(f"{palette.yellow}还没有候选回复{palette.reset}")
                continue
            index = last.best_index if last.best_index is not None else 0
            if rest.strip().isdigit():
                index = int(rest.strip()) - 1
            if not 0 <= index < len(last.replies):
                print(f"{palette.yellow}没有第 {rest.strip()} 条{palette.reset}")
                continue
            text = last.replies[index]
            tool = copy_to_clipboard(text)
            if tool:
                print(f"{palette.green}已复制第 {index + 1} 条（{tool}）：{text}{palette.reset}")
            else:
                print(f"{palette.yellow}没找到剪贴板工具（xclip/xsel/wl-copy），手动复制吧：{text}{palette.reset}")
            continue
        if command == "/json":
            if last is None:
                print(f"{palette.yellow}还没有分析结果{palette.reset}")
                continue
            print(json.dumps(last.to_record(time.strftime("%Y-%m-%d %H:%M:%S")),
                             ensure_ascii=False, indent=2))
            continue
        if command == "/go" or (not line.strip() and messages):
            if not messages:
                print(f"{palette.yellow}还没有消息{palette.reset}")
                continue
            if messages[-1].is_me:
                print(f"{palette.dim}提示：最后一条是你自己发的，判断会偏{palette.reset}")
            try:
                last = analyze(messages, cfg.relationship, judge, writer=writer, ranker=ranker,
                               do_rank=cfg.rank, judge_only=args.judge_only)
            except LLMError as exc:
                print(f"{palette.red}出错了：{exc}{palette.reset}")
                continue
            emit(last, cfg, palette)
            save_and_hint(last, cfg, palette)
            continue
        if line.strip().startswith("/"):
            print(f"{palette.dim}未知命令：{command}（/help 看帮助）{palette.reset}")
            continue

        parsed = parse_block(line, limit=0)
        if parsed:
            messages.extend(parsed)
            if len(messages) > MAX_MESSAGES:
                messages = messages[-MAX_MESSAGES:]
    return 0


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = apply_overrides(load_config(), args)
    command = (args.command or "").lower()

    if command in ("", "analyze", "a"):
        if not args.command and sys.stdin.isatty() and not args.args and not args.clip:
            return interactive(args, cfg)
        return cmd_analyze(args, cfg)
    if command in ("calibrate", "cal"):
        return cmd_calibrate(args, cfg)
    if command in ("config", "cfg"):
        return cmd_config(args, cfg)
    if command in ("logs", "log"):
        return cmd_logs(args, cfg)
    if command == "show":
        return cmd_show(args, cfg)
    if command == "help":
        parser.print_help()
        return 0
    print(f"不认识的子命令：{args.command}（analyze / calibrate / config / logs / show）",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
