import unittest

from jev.questions import (MAX_MESSAGES, QUESTIONS, build_rank_question, build_state,
                           closest_key, criteria_keys, spec_text)
from tests.helpers import msgs


class TestQuestionSet(unittest.TestCase):
    def test_seven_judge_questions(self):
        self.assertEqual(len(QUESTIONS), 7)
        for name in ("literal_question", "true_intent", "danger_level", "should_reply_now",
                     "best_action", "she_needs", "tension_resolved"):
            self.assertIn(name, QUESTIONS)

    def test_danger_has_ten_levels(self):
        self.assertEqual(len(QUESTIONS["danger_level"]["criteria"]), 10)
        self.assertEqual(QUESTIONS["danger_level"]["type"], "score")

    def test_instructions_are_english(self):
        """上游口径：题目措辞必须英文（判断模型主训练语言）。只有排序题的 criteria 是中文。"""
        for name, spec in QUESTIONS.items():
            self.assertRegex(spec["instructions"], r"^[A-Za-z]", msg=name)

    def test_criteria_keys(self):
        self.assertEqual(criteria_keys("true_intent"),
                         ["confirm_you_care", "vent_anger", "request_action",
                          "seek_explanation", "casual_chat", "close_topic"])
        self.assertEqual(criteria_keys("she_needs"),
                         ["apology", "action", "explanation", "care", "nothing"])
        self.assertEqual(criteria_keys("danger_level"), [])

    def test_closest_key(self):
        self.assertEqual(closest_key("she_needs", "care"), "care")
        self.assertEqual(closest_key("she_needs", "被重视"), "apology")  # 兜底取第一个 key
        self.assertEqual(closest_key("true_intent", "casual_chat 轻松聊天"), "casual_chat")


class TestBuildState(unittest.TestCase):
    def test_keeps_last_ten_and_maps_sides(self):
        messages = msgs(*[("other" if i % 2 else "me", f"msg{i}") for i in range(15)])
        state = build_state(messages, "friends")
        chat = state["chat"]
        self.assertEqual(len(chat["messages"]), MAX_MESSAGES)
        self.assertEqual(chat["messages"][0]["text"], "msg5")
        self.assertEqual(chat["relationship"], "friends")
        self.assertEqual(chat["latest_from"], messages[-1].side)
        self.assertEqual(chat["messages"][-1]["from"], "me")
        self.assertEqual(set(chat["messages"][0]), {"from", "text"})

    def test_empty_thread(self):
        state = build_state([], "friends")
        self.assertEqual(state["chat"]["messages"], [])
        self.assertEqual(state["chat"]["latest_from"], "other")

    def test_rank_question_needs_three(self):
        question = build_rank_question(["a", "b", "c"])["best_reply"]
        self.assertEqual(question["type"], "choice")
        self.assertEqual(list(question["criteria"]), ["reply_a", "reply_b", "reply_c"])
        with self.assertRaises(ValueError):
            build_rank_question(["a", "b"])


class TestSpecText(unittest.TestCase):
    def test_spec_covers_every_question(self):
        spec = spec_text()
        for name in QUESTIONS:
            self.assertIn(f"[{name}]", spec)
        self.assertIn("danger_level", spec)
        self.assertIn("JSON", spec)
        self.assertIn("level 0", spec)


if __name__ == "__main__":
    unittest.main()
