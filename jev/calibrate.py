"""校准：在标注集上跑 judge，出每题命中率 / danger 平均绝对误差 / 门禁判定。

标注集格式（兼容上游 332_lab-jev-chat 的 fixtures/labeled_set.json）：
    [{"id": "c01", "relationship": "friends",
      "messages": [["her", "今天下雨了，你带伞了吗"], ["me", "带了"]],
      "expect": {"literal_question": true, "true_intent": "casual_chat",
                 "danger_level": 0, "should_reply_now": false,
                 "best_action": "acknowledge", "she_needs": "nothing",
                 "tension_resolved": true}}]
`expect` 里少写哪题，那题就不计入命中率。

门禁（沿用上游验收口径）：
    danger_level 平均绝对误差 < 1.0 档
    true_intent 命中率 ≥ 60%
    she_needs 命中率 ≥ 60%
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from .llm import LLMError
from .model import Message
from .questions import CHOICE_KEYS, NOUL_KEYS, QUESTIONS, SCORE_KEYS

SLEEP_BETWEEN = 0.3
DANGER_MAE_MAX = 1.0
CHOICE_HIT_MIN = 0.60


def load_cases(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("标注集必须是 JSON 数组")
    for case in data:
        if not case.get("messages") or not case.get("expect"):
            raise SystemExit(f"标注集里 {case.get('id')} 缺 messages 或 expect")
    return data


def case_messages(case: dict) -> list[Message]:
    out = []
    for item in case["messages"]:
        who = item[0] if not isinstance(item, dict) else item.get("from")
        text = item[1] if not isinstance(item, dict) else item.get("text")
        side = "me" if who == "me" else "other"
        out.append(Message(side, str(text)))
    return out


def predicted_for(name: str, judgment) -> object:
    return getattr(judgment, name)


def hit_for(name: str, predicted, expect) -> bool | None:
    if expect is None:
        return None
    if name in NOUL_KEYS:
        return (float(predicted) >= 0.5) == bool(expect)
    if name in CHOICE_KEYS:
        return str(predicted) == str(expect)
    if name in SCORE_KEYS:
        try:
            return abs(float(predicted) - float(expect)) < 1.0
        except (TypeError, ValueError):
            return False
    return None


def run_case(case: dict, judge) -> dict:
    messages = case_messages(case)
    start = time.perf_counter()
    try:
        judgment, usage = judge.judge(messages, case.get("relationship", ""))
    except LLMError as exc:
        return {"id": case.get("id"), "ok": False, "error": str(exc),
                "expect": case.get("expect"), "hit": {}, "predicted": {}}
    latency = time.perf_counter() - start
    expect = case.get("expect") or {}
    row = {"id": case.get("id"), "ok": True, "latency_s": round(latency, 3),
           "usage": usage, "expect": expect, "predicted": {}, "confidence": {}, "hit": {},
           "diff": {}}
    for name in QUESTIONS:
        predicted = predicted_for(name, judgment)
        row["predicted"][name] = predicted
        confidence = (judgment.confidence or {}).get(name)
        row["confidence"][name] = confidence
        hit = hit_for(name, predicted, expect.get(name))
        row["hit"][name] = hit
        if hit is False:
            row["diff"][name] = {"expect": expect.get(name), "predicted": predicted}
    return row


def run_cases(cases: list[dict], judge, *, limit: int | None = None, sleep: float = SLEEP_BETWEEN,
              on_row=None) -> list[dict]:
    selected = cases[:limit] if limit else cases
    rows = []
    for index, case in enumerate(selected):
        row = run_case(case, judge)
        rows.append(row)
        if on_row:
            on_row(index + 1, len(selected), row)
        if index < len(selected) - 1 and sleep:
            time.sleep(sleep)
    return rows


def summarize(rows: list[dict]) -> dict:
    per_question: dict = {}
    hits: dict = defaultdict(list)
    confidences: dict = defaultdict(list)
    errors: list[float] = []
    for row in rows:
        if not row.get("ok"):
            continue
        for name in QUESTIONS:
            hit = (row.get("hit") or {}).get(name)
            if hit is not None:
                hits[name].append(bool(hit))
            confidence = (row.get("confidence") or {}).get(name)
            if confidence is not None:
                confidences[name].append(float(confidence))
        predicted = (row.get("predicted") or {}).get("danger_level")
        expect = (row.get("expect") or {}).get("danger_level")
        if predicted is not None and expect is not None:
            errors.append(abs(float(predicted) - float(expect)))

    for name in QUESTIONS:
        bucket = hits.get(name) or []
        confidence_bucket = confidences.get(name) or []
        item = {
            "n": len(bucket),
            "hit_rate": (sum(bucket) / len(bucket)) if bucket else None,
            "avg_confidence": (sum(confidence_bucket) / len(confidence_bucket))
            if confidence_bucket else None,
        }
        if name in SCORE_KEYS:
            item["mae"] = (sum(errors) / len(errors)) if errors else None
        per_question[name] = item

    latencies = [float(r["latency_s"]) for r in rows if r.get("latency_s") is not None]
    input_tokens = sum(int((r.get("usage") or {}).get("input_tokens")
                           or (r.get("usage") or {}).get("prompt_tokens") or 0)
                       for r in rows if r.get("ok"))
    output_tokens = sum(int((r.get("usage") or {}).get("output_tokens")
                            or (r.get("usage") or {}).get("completion_tokens") or 0)
                        for r in rows if r.get("ok"))
    cost = sum(float((r.get("usage") or {}).get("cost") or 0) for r in rows if r.get("ok"))
    danger_mae = per_question.get("danger_level", {}).get("mae")

    def _rate(name: str):
        return (per_question.get(name) or {}).get("hit_rate")

    return {
        "n_cases": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "n_errors": sum(1 for r in rows if not r.get("ok")),
        "per_question": per_question,
        "danger_level_mae": danger_mae,
        "avg_latency_s": (sum(latencies) / len(latencies)) if latencies else None,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_cost": cost,
        "gates": {
            "danger_level_mae_lt_1": bool(danger_mae is not None and danger_mae < DANGER_MAE_MAX),
            "true_intent_hit_ge_60": bool(_rate("true_intent") is not None
                                          and _rate("true_intent") >= CHOICE_HIT_MIN),
            "she_needs_hit_ge_60": bool(_rate("she_needs") is not None
                                        and _rate("she_needs") >= CHOICE_HIT_MIN),
        },
    }


def render_table(summary: dict) -> str:
    def pct(value):
        return "-" if value is None else f"{value * 100:5.1f}%"

    def num(value, digits=3):
        return "-" if value is None else f"{value:.{digits}f}"

    lines = [f"{'question':<20}{'hit':>8}{'mae':>9}{'avg_conf':>10}{'n':>5}", "-" * 52]
    for name, item in summary["per_question"].items():
        mae = num(item.get("mae")) if "mae" in item else "-"
        lines.append(f"{name:<20}{pct(item.get('hit_rate')):>8}{mae:>9}"
                     f"{num(item.get('avg_confidence')):>10}{item.get('n') or 0:>5}")
    lines.append("-" * 52)
    lines.append(f"n={summary['n_cases']}  ok={summary['n_ok']}  errors={summary['n_errors']}  "
                 f"avg_latency={num(summary['avg_latency_s'])}s  "
                 f"tokens_in={summary['total_input_tokens']}  tokens_out={summary['total_output_tokens']}")
    gates = summary["gates"]
    lines.append("gates: "
                 f"danger_mae<1.0={gates['danger_level_mae_lt_1']}  "
                 f"true_intent>=60%={gates['true_intent_hit_ge_60']}  "
                 f"she_needs>=60%={gates['she_needs_hit_ge_60']}")
    return "\n".join(lines)


def render_md(summary: dict, rows: list[dict], *, judge: str, fixtures: str,
              generated_at: str) -> str:
    lines = ["# 校准报告", "",
             f"- 生成时间：{generated_at}",
             f"- judge 后端：{judge}",
             f"- 标注集：{fixtures}",
             f"- 样本数：{summary['n_cases']}（成功 {summary['n_ok']}，失败 {summary['n_errors']}）",
             "", "## 汇总", "", "```", render_table(summary), "```", "",
             "## 逐条差异", ""]
    for row in rows:
        cid = row.get("id")
        if not row.get("ok"):
            lines.append(f"- `{cid}` 请求失败：{row.get('error')}")
            continue
        diffs = row.get("diff") or {}
        if not diffs:
            lines.append(f"- `{cid}` 全部标注项命中")
            continue
        bits = []
        for name, diff in diffs.items():
            bits.append(f"{name}: 标注={diff.get('expect')!r} 判到={diff.get('predicted')!r}")
        lines.append(f"- `{cid}` " + "；".join(bits))
    lines.append("")
    return "\n".join(lines)


def write_report(out_dir: Path, summary: dict, rows: list[dict], *, judge: str,
                 fixtures: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    payload = {"generated_at": generated_at, "judge": judge, "fixtures": str(fixtures),
               "summary": summary, "cases": rows}
    json_path = out_dir / "calibration.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
    md_path = out_dir / "calibration.md"
    md_path.write_text(render_md(summary, rows, judge=judge, fixtures=str(fixtures),
                                 generated_at=generated_at), encoding="utf-8")
    return json_path, md_path


__all__ = ["load_cases", "case_messages", "run_case", "run_cases", "summarize",
           "render_table", "render_md", "write_report", "predicted_for", "hit_for"]
