"""judge / writer / ranker 后端。

三段式的分工（照搬上游原理）：
    judge    结构化判断，只答选择题/打分/是非，永不生成正文
    writer   按 judge 的结论起草 3 条候选，禁止自己重新判断
    ranker   给 3 条候选排序，选最该发的一条

judge 有两种实现：
    deepseek  一个通用模型直接输出那 7 个字段（默认，只需要 DeepSeek key）
    jev       TypeSafe Jev 判断模型，走 OpenRouter（原版口径，需要 OPENROUTER_API_KEY）
writer 只有 deepseek（上游也是用生成模型起草）。
ranker 跟着 judge 走：jev 模式下由 Jev 排序，deepseek 模式下由同一个模型当裁判。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from .llm import LLMError, deepseek_chat, openrouter_decisions
from .model import Judgment, Message, Usage
from .questions import (CHOICE_KEYS, NOUL_KEYS, QUESTIONS, build_rank_question, build_state,
                        closest_key, spec_text)
from .labels import ACTION_LABELS, INTENT_LABELS, NEED_LABELS

REPLY_SLOTS = (
    "① 按「最佳动作」直接办（该道歉就道歉、该给承诺就给承诺、该查记录就说去查）",
    "② 稳妥版：先把状态/情绪接住或拖延一下，不承诺任何没确认的事实",
    "③ 另一条策略明显不同的备选（例如更简短、更主动约时间、或换个切入角度）",
)


def _as_probability(value, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _as_level(value, default: float = 0.0) -> float:
    try:
        return max(0.0, min(9.0, float(value)))
    except (TypeError, ValueError):
        return default


def _transcript(messages: list[Message]) -> str:
    return "\n".join(f"{'我' if m.is_me else '对方'}：{m.text}" for m in messages)


class JudgeBackend(ABC):
    kind = "abstract"

    @abstractmethod
    def judge(self, messages: list[Message], relationship: str) -> tuple[Judgment, dict]:
        """返回 (Judgment, usage dict)。"""


class DeepSeekJudge(JudgeBackend):
    """通用模型自判：一次调用拿全部 7 个字段。"""

    kind = "deepseek"

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.api_key = api_key
        self.model = model
        self._system = spec_text()

    def judge(self, messages, relationship):
        content, usage = deepseek_chat(
            self.api_key,
            [{"role": "system", "content": self._system},
             {"role": "user", "content": f"关系：{relationship}\n对话：\n{_transcript(messages)}"}],
            model=self.model, temperature=0.2, timeout=90, label="judge")
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"判断结果不是合法 JSON：{content[:200]}") from None
        judgment = Judgment(
            literal_question=_as_probability(raw.get("literal_question")),
            true_intent=closest_key("true_intent", str(raw.get("true_intent", ""))),
            danger_level=_as_level(raw.get("danger_level")),
            should_reply_now=_as_probability(raw.get("should_reply_now")),
            best_action=closest_key("best_action", str(raw.get("best_action", ""))),
            she_needs=closest_key("she_needs", str(raw.get("she_needs", ""))),
            tension_resolved=_as_probability(raw.get("tension_resolved")),
            reason=str(raw.get("reason", "")),
            raw=raw,
        )
        return judgment, usage


class JevJudge(JudgeBackend):
    """原版口径：TypeSafe Jev，一次请求发全部题目，返回概率/置信度。"""

    kind = "jev"

    def __init__(self, api_key: str, model: str = "") -> None:
        self.api_key = api_key
        self.model = model

    def judge(self, messages, relationship):
        response = openrouter_decisions(self.api_key, build_state(messages, relationship),
                                        QUESTIONS, model=self.model, label="judge")
        answers = response.get("answers") or {}
        judgment = Judgment(confidence={})
        for name, answer in answers.items():
            if not isinstance(answer, dict):
                continue
            if "confidence" in answer:
                judgment.confidence[name] = answer["confidence"]
            elif "noul" in answer:
                judgment.confidence[name] = abs(float(answer["noul"]) - 0.5) * 2
            if name in NOUL_KEYS:
                setattr(judgment, name, _as_probability(answer.get("noul")))
            elif name in CHOICE_KEYS:
                setattr(judgment, name, str(answer.get("choice", "")))
            elif name == "danger_level":
                probabilities = answer.get("probabilities") or {}
                try:
                    judgment.danger_level = sum(int(k) * float(p) for k, p in probabilities.items())
                except (TypeError, ValueError):
                    judgment.danger_level = _as_level(answer.get("score"))
        judgment.raw = answers
        return judgment, response.get("usage") or {}


class Writer:
    """生成 3 条候选回复。不做判断，只按 judge 的结论写。"""

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.api_key = api_key
        self.model = model

    def _constraint(self, judgment: Judgment) -> dict:
        return {
            "真实意图": INTENT_LABELS.get(judgment.true_intent, judgment.true_intent),
            "危险等级_0到9": round(judgment.danger_level, 1),
            "对方需要": NEED_LABELS.get(judgment.she_needs, judgment.she_needs),
            "最佳动作": ACTION_LABELS.get(judgment.best_action, judgment.best_action),
            "该给实质内容_概率": round(judgment.should_reply_now, 2),
            "紧张已解除_概率": round(judgment.tension_resolved, 2),
            "判断理由": judgment.reason,
        }

    def draft(self, messages: list[Message], relationship: str,
              judgment: Judgment) -> tuple[list[str], dict]:
        system = ("你是谨慎的中文聊天回复助手。判断已经由上游结构化模型完成（见「判断」字段），"
                  "你不做判断，只负责据此起草回复。给恰好三条建议，每条一到两句、口语化，"
                  "严格按槽位分工：\n" + "\n".join(REPLY_SLOTS) + "\n"
                  "三条必须在策略上明显不同，严禁同一句话的改写，严禁三条都写同一件事。\n"
                  "严禁编造事实、记忆、承诺或时间。如果最佳动作是「先查聊天记录」，"
                  "就把「我去翻一下记录再回你」放在①，而不是假装记得。"
                  '只输出 JSON：{"replies":["...","...","..."]}')
        content, usage = deepseek_chat(
            self.api_key,
            [{"role": "system", "content": system},
             {"role": "user", "content":
              f"关系：{relationship}\n判断：{json.dumps(self._constraint(judgment), ensure_ascii=False)}\n"
              f"对话：\n{_transcript(messages)}"}],
            model=self.model, temperature=0.8, timeout=90, label="draft")
        try:
            replies = json.loads(content).get("replies") or []
        except json.JSONDecodeError as exc:
            raise LLMError(f"生成结果不是合法 JSON：{content[:200]}") from None
        cleaned = [str(item).strip() for item in replies if str(item).strip()]
        if len(cleaned) != 3:
            raise LLMError(f"生成模型没有给够 3 条候选（拿到 {len(cleaned)} 条）")
        return cleaned, usage


class Ranker(ABC):
    kind = "abstract"

    @abstractmethod
    def rank(self, messages: list[Message], relationship: str, judgment: Judgment,
             replies: list[str]) -> tuple[int, str, dict]:
        """返回 (最合适的下标, 理由, usage)。"""


class DeepSeekRanker(Ranker):
    kind = "deepseek"

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.api_key = api_key
        self.model = model

    def rank(self, messages, relationship, judgment, replies):
        constraint = {
            "真实意图": INTENT_LABELS.get(judgment.true_intent, judgment.true_intent),
            "对方需要": NEED_LABELS.get(judgment.she_needs, judgment.she_needs),
            "最佳动作": ACTION_LABELS.get(judgment.best_action, judgment.best_action),
            "危险等级_0到9": round(judgment.danger_level, 1),
            "该给实质内容_概率": round(judgment.should_reply_now, 2),
        }
        numbered = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(replies))
        content, usage = deepseek_chat(
            self.api_key,
            [{"role": "system", "content":
              "你是回复质量裁判。给定对话、上游结构化判断和三条候选回复，选出最该发的一条。"
              "优先与「最佳动作」一致的候选；敷衍、过度承诺、答非所问的降权；"
              "事实还没确认时，优先选那条说去核实的，而不是假装记得或空洞道歉。"
              '只输出 JSON：{"best_index":0,"reason":"一句中文理由"}'},
             {"role": "user", "content":
              f"判断：{json.dumps(constraint, ensure_ascii=False)}\n对话：\n{_transcript(messages)}\n"
              f"候选：\n{numbered}"}],
            model=self.model, temperature=0.1, timeout=90, label="rank")
        try:
            raw = json.loads(content)
            index = int(raw.get("best_index", 0))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise LLMError(f"排序结果不可用：{content[:200]}") from None
        return max(0, min(len(replies) - 1, index)), str(raw.get("reason", "")), usage


class JevRanker(Ranker):
    kind = "jev"

    def __init__(self, api_key: str, model: str = "") -> None:
        self.api_key = api_key
        self.model = model

    def rank(self, messages, relationship, judgment, replies):
        names = ("reply_a", "reply_b", "reply_c")
        response = openrouter_decisions(self.api_key, build_state(messages, relationship),
                                        build_rank_question(replies), model=self.model, label="rank")
        answer = (response.get("answers") or {}).get("best_reply") or {}
        chosen = str(answer.get("choice", ""))
        index = names.index(chosen) if chosen in names else 0
        return index, "", response.get("usage") or {}


def build_judge(kind: str, model: str, deepseek_key: str, openrouter_key: str) -> JudgeBackend:
    if kind == "jev":
        if not openrouter_key:
            raise LLMError("judge=jev 需要 OPENROUTER_API_KEY（Jev 走 OpenRouter）")
        return JevJudge(openrouter_key, "")
    if kind == "deepseek":
        if not deepseek_key:
            raise LLMError("judge=deepseek 需要 DeepSeek API key（设 DEEPSEEK_API_KEY）")
        return DeepSeekJudge(deepseek_key, model)
    raise LLMError(f"不认识的 judge 类型：{kind}（可选 deepseek / jev）")


def build_writer(deepseek_key: str, model: str) -> Writer:
    if not deepseek_key:
        raise LLMError("生成候选回复需要 DeepSeek API key（设 DEEPSEEK_API_KEY）")
    return Writer(deepseek_key, model)


def build_ranker(kind: str, model: str, deepseek_key: str, openrouter_key: str) -> Ranker:
    if kind == "jev":
        if not openrouter_key:
            raise LLMError("judge=jev 时排序也走 Jev，需要 OPENROUTER_API_KEY")
        return JevRanker(openrouter_key, "")
    if not deepseek_key:
        raise LLMError("排序需要 DeepSeek API key（设 DEEPSEEK_API_KEY）")
    return DeepSeekRanker(deepseek_key, model)


def build_backends(kind: str, model: str, deepseek_key: str, openrouter_key: str):
    """按 judge 类型组装 (judge, writer, ranker)。"""
    return (build_judge(kind, model, deepseek_key, openrouter_key),
            build_writer(deepseek_key, model),
            build_ranker(kind, model, deepseek_key, openrouter_key))


__all__ = ["JudgeBackend", "DeepSeekJudge", "JevJudge", "Writer", "Ranker",
           "DeepSeekRanker", "JevRanker", "build_backends",
           "build_judge", "build_writer", "build_ranker"]
