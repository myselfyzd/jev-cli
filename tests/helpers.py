"""测试用的假后端：不碰网络。"""

from __future__ import annotations

from jev.model import Judgment, Message


class FakeJudge:
    kind = "fake"

    def __init__(self, judgment: Judgment | None = None, table: dict | None = None) -> None:
        self.judgment = judgment or Judgment(
            literal_question=0.9, true_intent="casual_chat", danger_level=0.0,
            should_reply_now=0.1, best_action="acknowledge", she_needs="nothing",
            tension_resolved=0.9, reason="假判断")
        self.table = table or {}
        self.calls: list = []

    def judge(self, messages: list[Message], relationship: str):
        self.calls.append((list(messages), relationship))
        return self.table.get(messages[-1].text, self.judgment), \
            {"input_tokens": 100, "output_tokens": 10}


class FakeWriter:
    kind = "fake"

    def __init__(self, replies: list[str] | None = None, usage: dict | None = None) -> None:
        self.replies = replies or ["候选一", "候选二", "候选三"]
        self.usage = usage if usage is not None else {"input_tokens": 200, "output_tokens": 30}
        self.calls: list = []

    def draft(self, messages, relationship, judgment):
        self.calls.append((list(messages), relationship, judgment))
        return list(self.replies), dict(self.usage)


class FakeRanker:
    kind = "fake"

    def __init__(self, index: int = 1, usage: dict | None = None) -> None:
        self.index = index
        self.usage = usage if usage is not None else {"input_tokens": 50, "output_tokens": 5}

    def rank(self, messages, relationship, judgment, replies):
        return self.index, "假理由", dict(self.usage)


def msgs(*pairs) -> list[Message]:
    return [Message(side, text) for side, text in pairs]
