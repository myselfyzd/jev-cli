import tempfile
import unittest
from pathlib import Path

from jev.model import Judgment, Message, Usage
from jev.pipeline import analyze
from jev.store import list_records, read_record, save_record
from tests.helpers import FakeJudge, FakeRanker, FakeWriter, msgs


def make_result():
    return analyze(msgs(("other", "你最好是"), ("me", "我去翻记录")), "情侣",
                   FakeJudge(judgment=Judgment(true_intent="confirm_you_care", danger_level=5.0,
                                               she_needs="care", best_action="check_history")),
                   writer=FakeWriter(), ranker=FakeRanker(index=0))


class TestStore(unittest.TestCase):
    def test_save_read_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            path = save_record(make_result(), log_dir, ts="2026-09-27 12:00:00")
            self.assertTrue(path.exists())
            same = save_record(make_result(), log_dir, ts="2026-09-27 12:00:00")
            self.assertNotEqual(path, same)  # 同一秒不覆盖

            data = read_record(path)
            self.assertEqual(data["relationship"], "情侣")
            self.assertEqual(data["judgment"]["true_intent"], "confirm_you_care")

            rows = list_records(log_dir, limit=5)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["intent"], "确认你是否在乎")
            self.assertEqual(rows[0]["band"], "公开不满")  # danger 5.0 -> 第 5 档
            self.assertEqual(rows[0]["preview"], "我去翻记录")

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_records(Path(tmp) / "nope"), [])

    def test_usage_merge(self):
        usage = Usage()
        usage.merge({"input_tokens": 10, "output_tokens": 2, "cost": 0.5})
        usage.merge({"prompt_tokens": 5, "completion_tokens": 3, "nested": {"x": 1}})
        self.assertEqual(usage.input_tokens, 15)
        self.assertEqual(usage.output_tokens, 5)
        self.assertAlmostEqual(usage.cost, 0.5)

    def test_message_rejects_bad_side(self):
        with self.assertRaises(ValueError):
            Message("them", "hi")


if __name__ == "__main__":
    unittest.main()
