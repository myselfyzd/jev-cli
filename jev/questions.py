"""固定题目集 —— 整个项目的核心资产。

英文 instructions/criteria 原样取自开源项目 332_lab-jev-chat
(https://github.com/Liyucheng1997/332_lab-jev-chat, MIT, tools/jev/questions.py)。

这些措辞是上游踩坑换来的，别随手改。作者在任务书里记下的两个实测矛盾：
  1) should_answer_now 给 0.77，同时 best_action 给"先翻聊天记录" 0.60 —— 两题互相打架。
     所以 should_reply_now 被限定成"下一条消息是否该含实质内容"，best_action 只描述动作类型。
  2) 对话已经收尾时 she_needs 判成"行动" 0.62 压过"什么都不用了" 0.38 —— 错。
     所以 she_needs 加了明确的 nothing 档，并在 instructions 里点明"对方已表示满意必须选 nothing"。

三条口径（上游定死，照抄）：
  * instructions / criteria 一律英文（判断模型主训练语言是英文），state 里的聊天内容保留中文原文；
  * 一次请求把 7 道判断题全发（speculative fan-out，省时省钱），排序题另发一次；
  * `from` 只用 me / other（上游 Jev 口径写 her / me，语义相同）。
"""

from __future__ import annotations

MAX_MESSAGES = 10  # 只带最近 10 条，和上游一致

NOUL_KEYS = ("literal_question", "should_reply_now", "tension_resolved")
CHOICE_KEYS = ("true_intent", "best_action", "she_needs")
SCORE_KEYS = ("danger_level",)

QUESTIONS: dict = {
    "literal_question": {
        "type": "noul",
        "instructions": (
            "Is the other person's latest message meant purely literally, with no subtext? "
            "Judge from the whole thread, not one sentence in isolation."
        ),
        "criteria": {
            "true": (
                "The latest message is a straightforward statement, question, or plan "
                "with no implied accusation, test, sarcasm, hint, or unsaid request."
            ),
            "false": (
                "There is subtext: a test of whether you remember or care, sarcasm, "
                "an implied complaint, a hint they will not say outright, a trap question, "
                "an accusation dressed as a question, or a cold/short line that really means blame."
            ),
        },
    },
    "true_intent": {
        "type": "choice",
        "instructions": (
            "What is the other person's true intent in the latest message, given the full conversation? "
            "Prefer tone and context over surface wording. "
            "If they are checking whether you remember something or still care, choose confirm_you_care "
            "even if the words look like a request to 'say it' or to do something. "
            "If they already accepted and closed the matter peacefully, choose close_topic. "
            "Ending the relationship, deleting you, or 'don't talk to me' is vent_anger, never close_topic."
        ),
        "criteria": {
            "confirm_you_care": (
                "They are testing whether you remember, pay attention, or still care. "
                "Signals: 'did you forget again', 'then say it', 'you better', sarcastic 'busy person', "
                "asking you to prove you know a past conversation. "
                "If they mainly want a new deliverable or a yes on a time, do not use this."
            ),
            "vent_anger": (
                "They are angry or hurt and mainly want the feeling acknowledged. "
                "They are blaming or raising the temperature; a specific plan is not the main point yet."
            ),
            "request_action": (
                "They want a concrete action, time, deliverable, or commitment from you now, "
                "and this is a real ask, not a loyalty test."
            ),
            "seek_explanation": (
                "They want a factual explanation of why something happened. "
                "They asked why or what is going on, not mainly for an apology or a new plan."
            ),
            "casual_chat": (
                "Light talk, banter, sharing, teasing with a laugh, or friendly logistics "
                "with no emotional test and no conflict. A friend suggesting a meal time can be this "
                "if the thread is warm."
            ),
            "close_topic": (
                "Peaceful wrap-up only: they accepted an apology, confirmed a happy plan, said thanks, "
                "or clearly signaled they need nothing more. "
                "Not a breakup, not 'don't contact me', not sarcastic 'I'm used to it'."
            ),
        },
    },
    "danger_level": {
        "type": "score",
        "instructions": (
            "How close is this conversation to a fight or to hurting the relationship? "
            "Match the current scene. "
            "If they genuinely accepted an apology or confirmed a happy plan, score the cooled-down present, "
            "not an earlier complaint. "
            "If an ultimatum (break up, report to the boss, stop covering for you) is still in force "
            "and has not been withdrawn, stay in that high bin even if the latest line names a specific task."
        ),
        "criteria": [
            "Light chat or joking; no complaint, no test, no deadline.",
            "Mild tease or a small reminder that is easy to laugh off; a clumsy reply would only feel slightly awkward.",
            "A mild complaint or 'please remember next time' said without heat; they still send warm or practical follow-ups.",
            "Noticeable unhappiness; they mention being forgotten, ignored, or kept waiting, but still give you a chance to make it right.",
            "Sarcasm, cold short replies, or 'you better'; they are testing you, and a sloppy or fake-confident reply will escalate.",
            "Openly upset; they accuse you of not listening or not caring; they expect a real response, not a joke.",
            "Clearly angry and blaming you; a wrong reply will turn this into a fight.",
            "Last-chance warning. They will not cover for you, do not want to keep talking unless this changes, "
            "or tell you to finish a named checklist yourself because trust is almost gone.",
            "An ultimatum is already on the table even if they also give a practical next step: "
            "break up if you forget again, report you tonight, or stop working together if you miss this.",
            "Active rupture: they said it is over, told you not to reply, deleted you, or are exploding.",
        ],
    },
    "should_reply_now": {
        "type": "noul",
        "instructions": (
            "Should your next message contain substantive content? "
            "Substantive means: admitting a specific known fault, giving a concrete time/plan/deliverable, "
            "explaining facts you actually know, or reciting the recalled content they asked you to say. "
            "This is NOT 'should you send any message'. Timing is irrelevant. "
            "Answer FALSE if the thing they want you to recite or prove is not present in this snippet "
            "(you would be guessing). 'Then say it' / 'you better' while you are stalling is FALSE. "
            "Answer FALSE if they already accepted and closed the topic. "
            "Answer true only if the needed fact, plan, or named fault is already in this snippet."
        ),
        "criteria": {
            "true": (
                "The needed fact, named fault, or named time/place is already in this snippet, "
                "and they are waiting for that substance now."
            ),
            "false": (
                "Do not put substance in the next message: the recalled content is not in this snippet, "
                "they are testing whether you remember, a holding line is enough, "
                "saying less is safer, or they already closed the topic."
            ),
        },
    },
    "best_action": {
        "type": "choice",
        "instructions": (
            "What type of next action is best? Do not decide whether to send a message immediately. "
            "Ignore timing. Choose only the action type. "
            "If they asked you to recall a specific past message or event and you have not shown that you actually remember it, "
            "choose check_history - do not apologize or invent a plan instead."
        ),
        "criteria": {
            "check_history": (
                "Look up prior chat or facts before taking a position. "
                "Use when they ask you to repeat, recall, or prove you remember something specific."
            ),
            "apologize": (
                "Lead with a sincere apology for a real mistake or hurt already identified. "
                "Not for an unnamed forgotten thing when you should first find out what it was."
            ),
            "give_commitment": (
                "Give a concrete promise, deadline, or arrangement they asked for "
                "in a conflict or work-pressure setting."
            ),
            "explain": "Explain what happened or why, without leading with apology or a new plan.",
            "acknowledge": (
                "Show you heard them and care, without new facts, an apology, or a plan. "
                "Use for light chat or when they mainly need to feel seen."
            ),
            "say_less": (
                "Keep it short or add nothing. Extra words would over-explain, reopen a closed topic, "
                "or pour fuel on an ultimatum that told you not to talk."
            ),
            "make_plan": (
                "Propose or confirm logistics (time, place, task) for a non-conflict request "
                "such as a meal or a meeting."
            ),
        },
    },
    "she_needs": {
        "type": "choice",
        "instructions": (
            "What does the other person need from you right now? Judge the LATEST message first. "
            "If they genuinely accepted (thanks / got it / 没事了 / 那就这样 / 收到了 / 过去了), "
            "you MUST choose nothing, even if earlier they wanted action or an apology. "
            "Sarcastic 'I'm used to it', 'whatever', 'I don't want to hear it', 'don't bother coming' "
            "is NOT genuine satisfaction - do not choose nothing. "
            "If they asked you to recap a named time/place/date, choose action. "
            "If they are testing whether you remember or still care, and the content is unnamed, choose care."
        ),
        "criteria": {
            "apology": "They need a sincere apology for hurt or a mistake, and they have not accepted one yet.",
            "action": (
                "They need a concrete action, time, commitment, recap of a named fact, or follow-through, "
                "and they have not yet accepted one."
            ),
            "explanation": "They need a clear explanation of what happened or why, and have not received it.",
            "care": (
                "They need proof you remember, listen, or care - a loyalty or attention test - "
                "not yet a plan or an apology. Sarcastic 'I am used to it' belongs here, not nothing."
            ),
            "nothing": (
                "They need nothing further. Genuine acceptance, a peaceful closed topic, "
                "warm casual chat with no ask, or a rupture where they told you not to reply. "
                "Not sarcasm pretending to be fine."
            ),
        },
    },
    "tension_resolved": {
        "type": "noul",
        "instructions": (
            "Has interpersonal tension already been resolved? "
            "Answer true only if there was never tension, or the other person has clearly accepted, "
            "cooled down, joked again, or said it is fine. "
            "A sarcastic 'you better', an unanswered test, leftover blame, or an open ultimatum means false."
        ),
        "criteria": {
            "true": (
                "No remaining tension: they accepted, joked again, said it's fine, "
                "confirmed a happy plan, or the chat was never tense."
            ),
            "false": (
                "Tension is still present: they are waiting, testing, angry, sarcastic, "
                "issuing an ultimatum, or the issue is open."
            ),
        },
    },
}


def criteria_keys(name: str) -> list[str]:
    crit = QUESTIONS[name]["criteria"]
    if isinstance(crit, dict):
        return list(crit.keys())
    return []  # score 型是有序档位，没有 key


def closest_key(name: str, value: str) -> str:
    """通用模型偶尔输出中文或近义 key。做一次包含匹配，兜不住就取第一个 key。"""
    keys = criteria_keys(name)
    if not keys:
        return ""
    value = (value or "").strip()
    if value in keys:
        return value
    lowered = value.lower()
    for key in keys:
        if key in lowered or lowered in key:
            return key
    return keys[0]


def build_state(messages, relationship: str) -> dict:
    """messages: list[Message]，只带最近 MAX_MESSAGES 条。"""
    recent = list(messages)[-MAX_MESSAGES:]
    return {
        "chat": {
            "relationship": relationship,
            "messages": [{"from": m.side, "text": m.text} for m in recent],
            "latest_from": recent[-1].side if recent else "other",
        }
    }


def build_rank_question(candidates: list[str]) -> dict:
    """给定 3 条候选回复，产出 best_reply 选择题。

    这是全项目唯一允许 criteria 用中文的地方 —— 因为它就是待选内容本身。
    """
    if len(candidates) != 3:
        raise ValueError("build_rank_question 只接受 3 条候选回复")
    keys = ("reply_a", "reply_b", "reply_c")
    return {
        "best_reply": {
            "type": "choice",
            "instructions": (
                "Which candidate reply is the most appropriate next message, "
                "given the conversation and the other person's true need? "
                "Prefer a reply that matches the best action type. "
                "Penalize dismissive, over-promising, or off-topic replies. "
                "If the facts are not yet confirmed, prefer the candidate that looks them up "
                "instead of faking memory or a vague apology."
            ),
            "criteria": {key: text for key, text in zip(keys, candidates)},
        }
    }


def spec_text() -> str:
    """把题目集渲染成给通用模型（非 Jev）看的需求说明，要求输出同样的 JSON 字段。"""
    lines = [
        "You are a strict typed judge. Answer every question below about the LATEST message",
        "in the thread. The chat text is Chinese; keep it Chinese.",
        "Judge from the whole thread, not one sentence in isolation.",
        "",
    ]
    for name, spec in QUESTIONS.items():
        lines.append(f"[{name}] type={spec['type']}")
        lines.append(f"  instructions: {spec['instructions']}")
        crit = spec["criteria"]
        if isinstance(crit, list):
            for i, desc in enumerate(crit):
                lines.append(f"  level {i}: {desc}")
        else:
            for k, desc in crit.items():
                lines.append(f"  {k}: {desc}")
        lines.append("")
    lines += [
        "Return ONLY a JSON object with exactly these keys:",
        '  "literal_question": 0.0-1.0  (probability the answer is true)',
        '  "true_intent": one of the true_intent criteria keys',
        '  "danger_level": integer 0-9 (the level index chosen above)',
        '  "should_reply_now": 0.0-1.0 (probability true)',
        '  "best_action": one of the best_action criteria keys',
        '  "she_needs": one of the she_needs criteria keys',
        '  "tension_resolved": 0.0-1.0 (probability true)',
        '  "reason": one short Chinese sentence explaining the key call',
    ]
    return "\n".join(lines)
