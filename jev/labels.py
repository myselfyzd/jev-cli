"""中文展示标签。judge 返回的是英文 key，展示给人看时翻译成中文。"""

INTENT_LABELS = {
    "confirm_you_care": "确认你是否在乎",
    "vent_anger": "表达生气/受伤",
    "request_action": "要求具体行动",
    "seek_explanation": "寻求解释",
    "casual_chat": "轻松聊天",
    "close_topic": "结束话题",
}

ACTION_LABELS = {
    "check_history": "先查聊天记录",
    "apologize": "真诚道歉",
    "give_commitment": "给出具体承诺",
    "explain": "解释事实",
    "acknowledge": "先接住情绪",
    "say_less": "少说一点",
    "make_plan": "确定计划",
}

NEED_LABELS = {
    "apology": "道歉",
    "action": "行动",
    "explanation": "解释",
    "care": "被重视",
    "nothing": "无需追加",
}

# danger_level 0~9 的一句话档位说明（展示用，判断口径以 questions.py 的英文 criteria 为准）
DANGER_BANDS = [
    "轻松闲聊",
    "轻微调侃",
    "温和抱怨",
    "明显不快",
    "阴阳怪气/试探",
    "公开不满",
    "明确指责",
    "最后通牒",
    "通牒已在桌上",
    "彻底破裂",
]


def label(mapping: dict, key: str, fallback: str = "—") -> str:
    if not key:
        return fallback
    return mapping.get(key, key)


def danger_band(level: float) -> str:
    try:
        idx = max(0, min(len(DANGER_BANDS) - 1, int(round(float(level)))))
    except (TypeError, ValueError):
        return "—"
    return DANGER_BANDS[idx]
