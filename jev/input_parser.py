"""输入解析：把用户贴的对话变成 Message 列表。

规则很简单，能少猜就少猜：
    对方: 你今天是不是又忘了我跟你说过什么？     -> other
    我：记得，你先别提示我                      -> me
    你今天是不是又忘了我跟你说过什么？           -> other（不带前缀按对方算）
"""

from __future__ import annotations

from .model import Message
from .questions import MAX_MESSAGES

ME_WORDS = {"我", "me", "myself", "自己", "俺", "本人"}
OTHER_WORDS = {"对方", "他", "她", "ta", "它", "对面", "her", "him", "other", "friend"}
SEPARATORS = (":", "：")
PREFIX_SCAN = 8  # 只看行首这几个字符里有没有分隔符，避免把正文里的冒号当分隔符


def parse_line(line: str) -> Message:
    raw = line.rstrip("\n").rstrip("\r")
    head_part = raw[:PREFIX_SCAN]
    for sep in SEPARATORS:
        if sep in head_part:
            head, _, rest = head_part.partition(sep)
            word = head.strip().lower()
            if word in ME_WORDS:
                return Message("me", (rest + raw[PREFIX_SCAN:]).strip() if len(raw) > PREFIX_SCAN else rest.strip())
            if word in OTHER_WORDS:
                return Message("other", (rest + raw[PREFIX_SCAN:]).strip() if len(raw) > PREFIX_SCAN else rest.strip())
    return Message("other", raw.strip())


def parse_block(text: str, limit: int = MAX_MESSAGES) -> list[Message]:
    messages = [m for m in (parse_line(line) for line in text.splitlines()) if m.text]
    if limit and len(messages) > limit:
        messages = messages[-limit:]
    return messages


def looks_like_dialogue(text: str) -> bool:
    return len(parse_block(text)) >= 2


def format_transcript(messages: list[Message]) -> str:
    return "\n".join(f"{'我' if m.is_me else '对方'}：{m.text}" for m in messages)
