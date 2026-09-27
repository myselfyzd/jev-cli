"""三段式流水线：judge -> draft -> rank。不碰网络以外的任何状态，方便测试替换后端。"""

from __future__ import annotations

import time

from .model import AnalysisResult, Judgment, Message, Usage
from .llm import LLMError


def analyze(messages: list[Message], relationship: str, judge, *, writer=None, ranker=None,
            do_rank: bool = True, judge_only: bool = False) -> AnalysisResult:
    if not messages:
        raise LLMError("没有消息可分析")

    usage = Usage()
    timings: dict = {}

    start = time.perf_counter()
    judgment, judge_usage = judge.judge(messages, relationship)
    timings["judge"] = time.perf_counter() - start
    usage.merge(judge_usage)

    result = AnalysisResult(messages=list(messages), relationship=relationship,
                            judgment=judgment, backend=getattr(judge, "kind", "?"),
                            timings=timings, usage=usage)
    if judge_only:
        return result

    if writer is None:
        raise LLMError("没有配置生成后端，无法起草候选回复")
    start = time.perf_counter()
    replies, writer_usage = writer.draft(messages, relationship, judgment)
    timings["draft"] = time.perf_counter() - start
    usage.merge(writer_usage)
    result.replies = replies

    if do_rank and ranker is not None:
        start = time.perf_counter()
        best, reason, rank_usage = ranker.rank(messages, relationship, judgment, replies)
        timings["rank"] = time.perf_counter() - start
        usage.merge(rank_usage)
        result.best_index = best
        result.rank_reason = reason

    return result


__all__ = ["analyze", "Judgment"]
