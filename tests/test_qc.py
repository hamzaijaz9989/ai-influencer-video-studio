import tempfile
import unittest
from pathlib import Path

from studio_core.qc import validate_srt


class CaptionQualityTests(unittest.TestCase):
    def test_valid_srt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "captions.srt"
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,200\nHello there\n\n"
                "2\n00:00:01,300 --> 00:00:02,000\nWelcome back\n",
                encoding="utf-8",
            )
            result = validate_srt(path)
            self.assertTrue(result["valid"])
            self.assertEqual(result["cue_count"], 2)

    def test_rejects_empty_caption_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "captions.srt"
            path.write_text("", encoding="utf-8")
            result = validate_srt(path)
            self.assertFalse(result["valid"])
            self.assertEqual(result["cue_count"], 0)

    def test_rejects_overlapping_cues(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "captions.srt"
            path.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nFirst\n\n"
                "2\n00:00:01,500 --> 00:00:03,000\nSecond\n",
                encoding="utf-8",
            )
            result = validate_srt(path)
            self.assertFalse(result["valid"])
            self.assertTrue(any("overlaps" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
