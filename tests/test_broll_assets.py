import tempfile
import unittest
from pathlib import Path

from studio_core.broll_assets import resolve_broll_assets, build_broll_filter


class BrollAssetTests(unittest.TestCase):
    def test_matches_only_expected_local_video_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shot_4.mp4").write_bytes(b"fake")
            (root / "shot_5.jpg").write_bytes(b"not video")
            (root / "other.mp4").write_bytes(b"not matched")
            shots = [{"segment_index": 4, "edited_start_seconds": 2, "edited_end_seconds": 5}]
            result = resolve_broll_assets(shots, root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["asset_status"], "matched_user_supplied_asset")

    def test_missing_directory_returns_no_assets(self):
        self.assertEqual(resolve_broll_assets([], None), [])

    def test_filter_graph_replaces_only_time_window(self):
        graph, label = build_broll_filter(
            "base",
            [{"edited_start_seconds": 2.0, "edited_end_seconds": 5.0}],
            1,
        )
        self.assertIn("between(t,2.000,5.000)", graph)
        self.assertIn("[1:v]", graph)
        self.assertEqual(label, "broll_mix_0")


if __name__ == "__main__":
    unittest.main()
