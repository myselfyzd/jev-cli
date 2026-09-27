"""数据模型。

Message 是采集/输入的统一表示：side 只有 'me' / 'other' 两个值。
Judgment 是 judge 后端统一返回的结构化判断（不管后端是 Jev 还是通用模型）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .labels import ACTION_LABELS, INTENT_LABELS, NEED_LABELS, label

SIDES = ("me", "other")


@dataclass(frozen=True)
class Message:
    side: str
    text: str

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"side 只能是 {SIDES}，收到 {self.side!r}")

    @property
    def is_me(self) -> bool:
        return self.side == "me"

    def to_dict(self) -> dict:
        return {"from": self.side, "text": self.text}


@dataclass
class Judgment:
    """7 道判断题的结果。

    noul 字段（literal_question / should_reply_now / tension_resolved）是 0~1 概率；
    danger_level 是 0~9 的档位（Jev 给概率分布时取加权值，通用模型给整数）；
    choice 字段是 questions.py 里的 criteria key。
    """

    literal_question: float = 0.5
    true_intent: str = ""
    danger_level: float = 0.0
    should_reply_now: float = 0.5
    best_action: str = ""
    she_needs: str = ""
    tension_resolved: float = 0.5
    reason: str = ""
    confidence: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def want_substance(self) -> bool:
        return self.should_reply_now >= 0.5

    @property
    def resolved(self) -> bool:
        return self.tension_resolved >= 0.5

    @property
    def literal(self) -> bool:
        return self.literal_question >= 0.5

    @property
    def intent_label(self) -> str:
        return label(INTENT_LABELS, self.true_intent)

    @property
    def need_label(self) -> str:
        return label(NEED_LABELS, self.she_needs)

    @property
    def action_label(self) -> str:
        return label(ACTION_LABELS, self.best_action)

    def to_dict(self) -> dict:
        return {
            "literal_question": self.literal_question,
            "true_intent": self.true_intent,
            "danger_level": self.danger_level,
            "should_reply_now": self.should_reply_now,
            "best_action": self.best_action,
            "she_needs": self.she_needs,
            "tension_resolved": self.tension_resolved,
            "reason": self.reason,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Judgment":
        return cls(
            literal_question=float(data.get("literal_question", 0.5)),
            true_intent=str(data.get("true_intent", "")),
            danger_level=float(data.get("danger_level", 0.0)),
            should_reply_now=float(data.get("should_reply_now", 0.5)),
            best_action=str(data.get("best_action", "")),
            she_needs=str(data.get("she_needs", "")),
            tension_resolved=float(data.get("tension_resolved", 0.5)),
            reason=str(data.get("reason", "")),
            confidence=dict(data.get("confidence") or {}),
        )


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    def merge(self, other: dict) -> None:
        for key, attr in (("input_tokens", "input_tokens"), ("prompt_tokens", "input_tokens"),
                          ("output_tokens", "output_tokens"), ("completion_tokens", "output_tokens")):
            value = other.get(key)
            if isinstance(value, (int, float)):
                setattr(self, attr, getattr(self, attr) + int(value))
        cost = other.get("cost")
        if isinstance(cost, (int, float)):
            self.cost += float(cost)

    def to_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cost": self.cost}


@dataclass
class AnalysisResult:
    messages: list[Message]
    relationship: str
    judgment: Judgment
    replies: list[str] = field(default_factory=list)
    best_index: int | None = None
    rank_reason: str = ""
    timings: dict = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    backend: str = "deepseek"

    @property
    def best_reply(self) -> str:
        if self.best_index is None or not self.replies:
            return ""
        return self.replies[self.best_index]

    def to_record(self, ts: str) -> dict:
        return {
            "ts": ts,
            "backend": self.backend,
            "relationship": self.relationship,
            "messages": [m.to_dict() for m in self.messages],
            "judgment": self.judgment.to_dict(),
            "replies": self.replies,
            "best_index": self.best_index,
            "rank_reason": self.rank_reason,
            "timings": self.timings,
            "usage": self.usage.to_dict(),
        }
