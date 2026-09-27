import unittest

from jev.model import Judgment
from jev.pipeline import analyze
from jev.render import Palette, danger_bar, render, usage_line
from tests.helpers import FakeJudge, FakeRanker, FakeWriter, msgs

THREAD = msgs(("other", "你今天是不是又忘了我跟你说过什么？"), ("me", "记得"), ("other", "你最好是。"))
JUDGMENT = Judgment(literal_question=0.2, true_intent="confirm_you_care", danger_level=5.0,
                    should_reply_now=0.2, best_action="check_history", she_needs="care",
                    tension_resolved=0.1, reason="对方在测试你记不记得")


def make_result():
    return analyze(THREAD, "情侣", FakeJudge(judgment=JUDGMENT),
                   writer=FakeWriter(), ranker=FakeRanker(index=2))


class TestRender(unittest.TestCase):
    def test_plain_output_has_labels_and_marks(self):
        text = render(make_result(), Palette(False))
        self.assertIn("真实意图", text)
        self.assertIn("确认你是否在乎", text)
        self.assertIn("先查聊天记录", text)
        self.assertIn("被重视", text)
        self.assertIn("紧张未解除", text)
        self.assertIn("▍候选回复", text)
        self.assertIn("✔ 3. 候选三", text)
        self.assertIn("建议发第 3 条", text)
        self.assertNotIn("\033[", text)

    def test_color_output_has_ansi(self):
        text = render(make_result(), Palette(True))
        self.assertIn("\033[", text)

    def test_danger_bar_width(self):
        bar = danger_bar(5.0, Palette(False))
        self.assertEqual(bar.count("█") + bar.count("░"), 10)
        self.assertEqual(bar.count("█"), 6)

    def test_danger_colors(self):
        self.assertEqual(Palette(True).for_danger(1.0), "\033[32m")
        self.assertEqual(Palette(True).for_danger(5.0), "\033[33m")
        self.assertEqual(Palette(True).for_danger(8.0), "\033[31m")

    def test_usage_line(self):
        line = usage_line(make_result(), Palette(False))
        self.assertIn("tokens_in=", line)
        self.assertIn("判断", line)
        self.assertIn("排序", line)

    def test_judge_only_render(self):
        result = analyze(THREAD, "情侣", FakeJudge(judgment=JUDGMENT), judge_only=True)
        text = render(result, Palette(False))
        self.assertNotIn("▍候选回复", text)
        self.assertIn("提示", text)


if __name__ == "__main__":
    unittest.main()
