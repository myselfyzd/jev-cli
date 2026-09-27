import json
import tempfile
import unittest
from pathlib import Path

from jev.calibrate import (hit_for, load_cases, render_md, render_table, run_cases,
                           summarize, write_report)
from jev.model import Judgment
from tests.helpers import FakeJudge

CASES = [
    {"id": "c01", "relationship": "friends",
     "messages": [["her", "今天下雨了，你带伞了吗"], ["me", "带了"]],
     "expect": {"literal_question": True, "true_intent": "casual_chat", "danger_level": 0,
                "should_reply_now": False, "best_action": "acknowledge",
                "she_needs": "nothing", "tension_resolved": True}},
    {"id": "c02", "relationship": "romantic partners",
     "messages": [["her", "你今天是不是又忘了我跟你说过什么？"], ["me", "记得"], ["her", "那你说"]],
     "expect": {"literal_question": False, "true_intent": "confirm_you_care", "danger_level": 5,
                "should_reply_now": False, "best_action": "check_history",
                "she_needs": "care", "tension_resolved": False}},
]

JUDGMENTS = {
    "带了": Judgment(literal_question=0.9, true_intent="casual_chat", danger_level=0.0,
                     should_reply_now=0.1, best_action="acknowledge", she_needs="nothing",
                     tension_resolved=0.9),
    "那你说": Judgment(literal_question=0.2, true_intent="confirm_you_care", danger_level=5.0,
                      should_reply_now=0.2, best_action="check_history", she_needs="care",
                      tension_resolved=0.1),
}


class TestHitLogic(unittest.TestCase):
    def test_noul_uses_half_threshold(self):
        self.assertTrue(hit_for("should_reply_now", 0.7, True))
        self.assertFalse(hit_for("should_reply_now", 0.4, True))

    def test_choice_needs_exact_key(self):
        self.assertTrue(hit_for("true_intent", "casual_chat", "casual_chat"))
        self.assertFalse(hit_for("true_intent", "vent_anger", "casual_chat"))

    def test_score_within_one_level(self):
        self.assertTrue(hit_for("danger_level", 5.4, 5))
        self.assertFalse(hit_for("danger_level", 6.2, 5))

    def test_missing_label_is_ignored(self):
        self.assertIsNone(hit_for("true_intent", "casual_chat", None))


class TestRunAndSummarize(unittest.TestCase):
    def setUp(self):
        self.rows = run_cases(CASES, FakeJudge(table=JUDGMENTS), sleep=0)

    def test_all_hit(self):
        self.assertEqual(len(self.rows), 2)
        self.assertTrue(all(row["ok"] for row in self.rows))
        self.assertEqual(self.rows[0]["diff"], {})

    def test_summary_rates(self):
        summary = summarize(self.rows)
        self.assertEqual(summary["n_cases"], 2)
        self.assertEqual(summary["n_errors"], 0)
        self.assertAlmostEqual(summary["per_question"]["true_intent"]["hit_rate"], 1.0)
        self.assertAlmostEqual(summary["danger_level_mae"], 0.0)
        self.assertTrue(all(summary["gates"].values()))
        self.assertEqual(summary["total_input_tokens"], 200)

    def test_table_and_md(self):
        summary = summarize(self.rows)
        table = render_table(summary)
        self.assertIn("true_intent", table)
        self.assertIn("gates:", table)
        md = render_md(summary, self.rows, judge="fake", fixtures="x.json", generated_at="now")
        self.assertIn("c01", md)
        self.assertIn("全部标注项命中", md)

    def test_mismatch_is_recorded(self):
        wrong = dict(JUDGMENTS)
        wrong["那你说"] = Judgment(true_intent="vent_anger", danger_level=8.0, she_needs="apology",
                                 best_action="apologize", tension_resolved=0.1, literal_question=0.9,
                                 should_reply_now=0.9)
        rows = run_cases(CASES, FakeJudge(table=wrong), sleep=0)
        summary = summarize(rows)
        self.assertFalse(summary["gates"]["she_needs_hit_ge_60"])
        self.assertIn("true_intent", rows[1]["diff"])
        self.assertAlmostEqual(summary["danger_level_mae"], 1.5)
        md = render_md(summary, rows, judge="fake", fixtures="x.json", generated_at="now")
        self.assertIn("标注=", md)


class TestFixturesFile(unittest.TestCase):
    def test_ships_with_labeled_set(self):
        path = Path(__file__).resolve().parent.parent / "fixtures" / "labeled_set.json"
        self.assertTrue(path.exists(), "仓库应自带上游标注集，便于离线自查")
        cases = load_cases(path)
        self.assertGreaterEqual(len(cases), 25)
        for case in cases:
            self.assertIn("expect", case)
            self.assertIn("danger_level", case["expect"])

    def test_write_report(self):
        rows = run_cases(CASES, FakeJudge(table=JUDGMENTS), sleep=0)
        summary = summarize(rows)
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = write_report(Path(tmp), summary, rows, judge="fake",
                                              fixtures=Path("fixtures/labeled_set.json"))
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["n_cases"], 2)
            self.assertTrue(md_path.read_text(encoding="utf-8").startswith("# 校准报告"))


if __name__ == "__main__":
    unittest.main()
