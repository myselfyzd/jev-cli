import unittest

from jev.llm import LLMError
from jev.model import Judgment
from jev.pipeline import analyze
from tests.helpers import FakeJudge, FakeRanker, FakeWriter, msgs

THREAD = msgs(("other", "你今天是不是又忘了我跟你说过什么？"), ("me", "记得"),
              ("other", "你最好是。"))


class TestPipeline(unittest.TestCase):
    def test_full_three_stage_flow(self):
        judge, writer, ranker = FakeJudge(), FakeWriter(), FakeRanker(index=1)
        result = analyze(THREAD, "情侣", judge, writer=writer, ranker=ranker)

        self.assertEqual(len(judge.calls), 1)
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(len(result.replies), 3)
        self.assertEqual(result.best_index, 1)
        self.assertEqual(result.best_reply, "候选二")
        self.assertEqual(result.relationship, "情侣")
        for stage in ("judge", "draft", "rank"):
            self.assertIn(stage, result.timings)
            self.assertGreaterEqual(result.timings[stage], 0)

    def test_usage_is_summed_across_stages(self):
        result = analyze(THREAD, "情侣", FakeJudge(), writer=FakeWriter(), ranker=FakeRanker())
        self.assertEqual(result.usage.input_tokens, 100 + 200 + 50)
        self.assertEqual(result.usage.output_tokens, 10 + 30 + 5)

    def test_writer_receives_judgment(self):
        judgment = Judgment(true_intent="confirm_you_care", danger_level=6.0, best_action="check_history")
        writer = FakeWriter()
        analyze(THREAD, "情侣", FakeJudge(judgment=judgment), writer=writer, ranker=None)
        self.assertIs(writer.calls[0][2].true_intent, "confirm_you_care")

    def test_judge_only_skips_generation(self):
        writer = FakeWriter()
        result = analyze(THREAD, "情侣", FakeJudge(), writer=writer, judge_only=True)
        self.assertEqual(result.replies, [])
        self.assertEqual(writer.calls, [])
        self.assertNotIn("draft", result.timings)

    def test_rank_can_be_skipped(self):
        result = analyze(THREAD, "情侣", FakeJudge(), writer=FakeWriter(), ranker=None)
        self.assertEqual(len(result.replies), 3)
        self.assertIsNone(result.best_index)
        self.assertNotIn("rank", result.timings)

    def test_empty_thread_raises(self):
        with self.assertRaises(LLMError):
            analyze([], "情侣", FakeJudge())

    def test_record_roundtrip(self):
        result = analyze(THREAD, "情侣", FakeJudge(), writer=FakeWriter(), ranker=FakeRanker(index=2))
        record = result.to_record("2026-09-27 12:00:00")
        self.assertEqual(record["messages"][0]["from"], "other")
        self.assertEqual(record["best_index"], 2)
        self.assertEqual(record["judgment"]["true_intent"], "casual_chat")


if __name__ == "__main__":
    unittest.main()
