import json
import tempfile
import unittest
from pathlib import Path

from studio_core.editorial import review_repeated_lines
from studio_core.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def test_persists_completed_status(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            store = JobStore(path)
            store.set("source-key", "completed", output="final.mp4")
            restored = JobStore(path)
            self.assertEqual(restored.status("source-key"), "completed")


class EditorialTests(unittest.TestCase):
    def test_flags_repeated_lines_without_cutting(self):
        rows = [
            {"start": 1.0, "end": 4.0, "text": "The best way to learn driving is practice every day."},
            {"start": 8.0, "end": 11.0, "text": "The best way to learn driving is practice every day."},
        ]
        found = review_repeated_lines(rows)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["decision"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
