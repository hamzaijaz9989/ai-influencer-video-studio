import json
import tempfile
import unittest
from pathlib import Path

from studio_core.editorial import review_repeated_lines
from studio_core.job_store import JobStore
from studio import build_segment_encode_command


class JobStoreTests(unittest.TestCase):
    def test_persists_completed_status(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            store = JobStore(path)
            store.set("source-key", "completed", output="final.mp4")
            restored = JobStore(path)
            self.assertEqual(restored.status("source-key"), "completed")


class EditorialTests(unittest.TestCase):
    def test_transcript_signals_do_not_claim_delivery_quality(self):
        rows = [
            {"start": 0, "end": 3, "text": "This is the complete explanation."},
            {"start": 4, "end": 7, "text": "This is the complete explanation"},
        ]
        found = review_repeated_lines(rows)
        self.assertEqual(found[0]["review_first_segment_index"], 0)
        self.assertIn("cannot assess vocal delivery", __import__(
            "studio_core.editorial", fromlist=["build_editorial_review"]
        ).build_editorial_review(rows)["policy"])

    def test_flags_repeated_lines_without_cutting(self):
        rows = [
            {"start": 1.0, "end": 4.0, "text": "The best way to learn driving is practice every day."},
            {"start": 8.0, "end": 11.0, "text": "The best way to learn driving is practice every day."},
        ]
        found = review_repeated_lines(rows)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["decision"], "REVIEW_REQUIRED")
        self.assertIsNone(found[0]["review_first_segment_index"])
        self.assertTrue(found[0]["first_signals"]["complete_sentence_punctuation"])
        self.assertIn("transcript_completeness_score", found[0]["second_signals"])



class SegmentCommandTests(unittest.TestCase):
    def test_uses_duration_not_absolute_end_timestamp(self):
        args = build_segment_encode_command(Path("source.mp4"), Path("part.mp4"), 12.5, 18.0)
        self.assertEqual(args[args.index("-ss") + 1], "12.500")
        self.assertEqual(args[args.index("-t") + 1], "5.500")
        self.assertNotIn("-to", args)

    def test_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            build_segment_encode_command(Path("source.mp4"), Path("part.mp4"), 5.0, 5.0)



    def test_recovers_from_corrupt_state_without_overwriting_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text("{not valid json", encoding="utf-8")
            store = JobStore(path)
            self.assertIsNone(store.status("missing"))
            backup = path.with_suffix(".json.corrupt")
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_text(encoding="utf-8"), "{not valid json")
            store.set("new-key", "completed")
            self.assertEqual(JobStore(path).status("new-key"), "completed")

    def test_recovers_from_unsupported_state_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text(json.dumps({"version": 999, "jobs": {}}), encoding="utf-8")
            store = JobStore(path)
            self.assertIsNone(store.status("missing"))
            self.assertTrue(path.with_suffix(".json.corrupt").is_file())

if __name__ == "__main__":
    unittest.main()
