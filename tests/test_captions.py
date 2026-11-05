import tempfile
import unittest
from pathlib import Path

from studio_core.captions import build_ass


class StyledCaptionTests(unittest.TestCase):
    def test_writes_ass_and_highlights_director_words(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "captions.ass"
            segments = [
                {"start": 0.0, "end": 1.2, "text": "Learn AT driving today"},
                {"start": 2.0, "end": 3.0, "text": "Second sentence"},
            ]
            plan = {"caption_emphasis": [{"segment_index": 0, "words": ["AT", "today"]}]}
            count = build_ass(segments, [], path, plan)
            output = path.read_text(encoding="utf-8")
            self.assertEqual(count, 2)
            self.assertIn("{\\c&H0000FFFF&}AT", output)
            self.assertIn("Second sentence", output)

    def test_remaps_caption_after_removed_silence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "captions.ass"
            segments = [{"start": 5.0, "end": 6.0, "text": "After the pause"}]
            build_ass(segments, [[1.0, 4.0]], path)
            output = path.read_text(encoding="utf-8")
            self.assertIn("0:00:02.00,0:00:03.00", output)



    def test_escapes_transcript_override_sequences(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "captions.ass"
            segments = [{"start": 0.0, "end": 1.0, "text": r"Literal \\N and {override}"}]
            build_ass(segments, [], path)
            output = path.read_text(encoding="utf-8")
            self.assertIn(r"Literal \\\\N", output)
            self.assertIn(r"\\{override\\}", output)

if __name__ == "__main__":
    unittest.main()
