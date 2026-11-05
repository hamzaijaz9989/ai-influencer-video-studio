import json
import tempfile
import unittest
from pathlib import Path

from studio_core.revisions import DEFAULTS, load_revisions


class RevisionSettingsTests(unittest.TestCase):
    def test_missing_file_uses_defaults(self):
        self.assertEqual(load_revisions(None), DEFAULTS)

    def test_valid_values_override_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revisions.json"
            path.write_text(json.dumps({"smart_zoom_strength": 0.1}), encoding="utf-8")
            result = load_revisions(path)
        self.assertEqual(result["smart_zoom_strength"], 0.1)
        self.assertEqual(result["silence_min_seconds"], DEFAULTS["silence_min_seconds"])

    def test_unknown_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revisions.json"
            path.write_text(json.dumps({"shell_command": "rm -rf /"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_revisions(path)

    def test_out_of_range_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revisions.json"
            path.write_text(json.dumps({"smart_zoom_strength": 0.8}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_revisions(path)

    def test_boolean_is_not_accepted_as_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revisions.json"
            path.write_text(json.dumps({"silence_min_seconds": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_revisions(path)


if __name__ == "__main__":
    unittest.main()
