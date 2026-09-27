import json
import os
import tempfile
import unittest
from pathlib import Path

from jev import llm


class TestTrace(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("JEV_TRACE_DIR", None)

    def test_no_env_no_files(self):
        self.assertIsNone(llm._trace_dir())

    def test_writes_request_and_masks_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["JEV_TRACE_DIR"] = tmp
            llm._write_trace("judge", "https://example.invalid/x",
                             {"Authorization": "Bearer sk-abcdef1234567890"}, {"model": "m"},
                             response={"choices": [{"message": {"content": "{}"}}]})
            files = sorted(Path(tmp).glob("*.json"))
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].name.endswith("-judge.json"))
            entry = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(entry["label"], "judge")
            self.assertEqual(entry["request"]["body"], {"model": "m"})
            self.assertNotIn("sk-abcdef1234567890", json.dumps(entry))
            self.assertIn("已脱敏", entry["request"]["headers"]["Authorization"])
            self.assertIn("response", entry)

    def test_error_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["JEV_TRACE_DIR"] = tmp
            llm._write_trace("draft", "https://example.invalid/x", {}, {}, error="HTTP 500")
            entry = json.loads(next(Path(tmp).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(entry["error"], "HTTP 500")
            self.assertNotIn("response", entry)


if __name__ == "__main__":
    unittest.main()
