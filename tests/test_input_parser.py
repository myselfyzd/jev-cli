import unittest

from jev.input_parser import format_transcript, looks_like_dialogue, parse_block, parse_line


class TestParseLine(unittest.TestCase):
    def test_me_prefixes(self):
        for prefix in ("我", "me", "自己"):
            self.assertEqual(parse_line(f"{prefix}: 记得").side, "me")
            self.assertEqual(parse_line(f"{prefix}：记得").text, "记得")

    def test_other_prefixes(self):
        for prefix in ("对方", "他", "她", "her", "ta"):
            self.assertEqual(parse_line(f"{prefix}: 那你说").side, "other")

    def test_bare_line_defaults_to_other(self):
        message = parse_line("你今天是不是又忘了我跟你说过什么？")
        self.assertEqual(message.side, "other")
        self.assertEqual(message.text, "你今天是不是又忘了我跟你说过什么？")

    def test_colon_inside_text_is_not_a_prefix(self):
        text = "我昨天开会到很晚，你说的那个方案：我改完了，明天发你"
        message = parse_line(text)
        self.assertEqual(message.side, "other")
        self.assertEqual(message.text, text)

    def test_empty_text_dropped(self):
        self.assertEqual(parse_block("对方:\n我:\n"), [])


class TestParseBlock(unittest.TestCase):
    def test_order_and_limit(self):
        block = "\n".join(f"{'我' if i % 2 else '对方'}: 第{i}条" for i in range(13))
        messages = parse_block(block)
        self.assertEqual(len(messages), 10)
        self.assertEqual(messages[-1].text, "第12条")

    def test_limit_zero_means_no_limit(self):
        block = "\n".join(f"对方: 第{i}条" for i in range(13))
        self.assertEqual(len(parse_block(block, limit=0)), 13)

    def test_looks_like_dialogue(self):
        self.assertTrue(looks_like_dialogue("对方: 在吗\n我: 在"))
        self.assertFalse(looks_like_dialogue("就一句话"))

    def test_format_transcript(self):
        messages = parse_block("对方: 在吗\n我: 在")
        self.assertEqual(format_transcript(messages), "对方：在吗\n我：在")


if __name__ == "__main__":
    unittest.main()
