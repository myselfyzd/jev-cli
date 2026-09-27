"""本地记录：每次分析落一份 JSON，供回看和以后做校准。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .labels import INTENT_LABELS, danger_band
from .model import AnalysisResult


def save_record(result: AnalysisResult, log_dir: Path, ts: str | None = None) -> Path:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = ts or time.strftime("%Y-%m-%d %H:%M:%S")
    stamp = ts.replace("-", "").replace(":", "").replace(" ", "-")
    path = log_dir / f"{stamp}.json"
    suffix = 1
    while path.exists():
        path = log_dir / f"{stamp}-{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(result.to_record(ts), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def read_record(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def list_records(log_dir: Path, limit: int = 10) -> list[dict]:
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []
    files = sorted(log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    rows = []
    for path in files:
        try:
            data = read_record(path)
        except (json.JSONDecodeError, OSError):
            continue
        judgment = data.get("judgment") or {}
        messages = data.get("messages") or []
        last = messages[-1]["text"] if messages else ""
        rows.append({
            "path": path,
            "ts": data.get("ts", ""),
            "backend": data.get("backend", ""),
            "relationship": data.get("relationship", ""),
            "intent": INTENT_LABELS.get(judgment.get("true_intent", ""), judgment.get("true_intent", "")),
            "danger": judgment.get("danger_level", 0.0),
            "band": danger_band(judgment.get("danger_level", 0.0)),
            "best_index": data.get("best_index"),
            "preview": (last[:24] + "…") if len(last) > 24 else last,
        })
    return rows


__all__ = ["save_record", "read_record", "list_records"]
