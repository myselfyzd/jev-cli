import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jev import __version__
from jev.cli import apply_overrides, build_parser, cmd_config, cmd_logs, cmd_show, record_to_result
from jev.config import Config
from jev.pipeline import analyze
from tests.helpers import FakeJudge, FakeRanker, FakeWriter, msgs


def run_config(args_list, cfg=None):
    parser = build_parser()
    args = parser.parse_args(args_list)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cmd_config(args, cfg or Config())
    return code, buffer.getvalue()


class TestParser(unittest.TestCase):
    def test_defaults(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.command)
        self.assertEqual(args.n, 10)

    def test_analyze_with_flags(self):
        args = build_parser().parse_args(["analyze", "chat.txt", "-r", "情侣", "-j", "jev", "--json"])
        self.assertEqual(args.args, ["chat.txt"])
        cfg = apply_overrides(Config(), args)
        self.assertEqual(cfg.relationship, "情侣")
        self.assertEqual(cfg.judge, "jev")
        self.assertTrue(args.json)

    def test_calibrate_flags(self):
        args = build_parser().parse_args(["calibrate", "--limit", "5", "--sleep", "0", "--out", "/tmp/x"])
        self.assertEqual(args.limit, 5)
        self.assertEqual(args.sleep, 0.0)
        self.assertEqual(args.out, "/tmp/x")

    def test_version_string(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--version"])
        self.assertTrue(__version__)


class TestConfigCommand(unittest.TestCase):
    def test_show_masks_keys(self):
        cfg = Config(deepseek_api_key="sk-1234567890abcdef")
        code, out = run_config(["config", "show"], cfg)
        self.assertEqual(code, 0)
        self.assertIn("sk-123", out)
        self.assertNotIn("sk-1234567890abcdef", out)

    def test_unknown_action(self):
        code, _ = run_config(["config", "boom"])
        self.assertEqual(code, 2)

    def test_bad_field(self):
        code, _ = run_config(["config", "set", "nope", "1"])
        self.assertEqual(code, 2)


class TestLogsAndShow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(log_dir=self.tmp.name)
        result = analyze(msgs(("other", "你最好是")), "情侣",
                         FakeJudge(), writer=FakeWriter(), ranker=FakeRanker(index=1))
        from jev.store import save_record
        self.path = save_record(result, Path(self.tmp.name), ts="2026-09-27 12:00:00")

    def tearDown(self):
        self.tmp.cleanup()

    def test_logs_lists_records(self):
        parser = build_parser()
        args = parser.parse_args(["logs", "-n", "5"])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_logs(args, self.cfg)
        self.assertEqual(code, 0)
        self.assertIn("2026-09-27", buffer.getvalue())

    def test_show_latest(self):
        parser = build_parser()
        args = parser.parse_args(["show", "latest"])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_show(args, self.cfg)
        self.assertEqual(code, 0)
        self.assertIn("真实意图", buffer.getvalue())

    def test_show_missing(self):
        parser = build_parser()
        args = parser.parse_args(["show", "/nope/nope.json"])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_show(args, self.cfg)
        self.assertEqual(code, 2)

    def test_record_roundtrip_for_show(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        result = record_to_result(data)
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.judgment.true_intent, "casual_chat")
        self.assertEqual(result.best_index, 1)


if __name__ == "__main__":
    unittest.main()
