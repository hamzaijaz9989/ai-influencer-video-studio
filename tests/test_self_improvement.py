import json
import tempfile
import unittest
from pathlib import Path

from studio_core.self_improvement import (
    load_profile,
    profile_summary,
    recommend_revisions,
    record_feedback,
    record_render,
)


class SelfImprovementTests(unittest.TestCase):
    def test_recommendations_adapt_to_tracking_quality(self):
        base = {"smart_zoom_strength": 0.06, "silence_threshold_db": -38, "silence_min_seconds": 5}
        visual = {"frames_analyzed": 10, "face_detection_ratio": 0.1, "exposure": {}}
        result = recommend_revisions(base, visual, load_profile(Path("/missing/profile.json")))
        self.assertLess(result["smart_zoom_strength"], base["smart_zoom_strength"])
        self.assertEqual(result["silence_threshold_db"], -38)

    def test_negative_feedback_reduces_zoom_strength(self):
        profile = load_profile(Path("/missing/profile.json"))
        profile["feedback"]["worse"] = 3
        visual = {"frames_analyzed": 10, "face_detection_ratio": 0.9, "exposure": {}}
        result = recommend_revisions({"smart_zoom_strength": 0.06}, visual, profile)
        self.assertLess(result["smart_zoom_strength"], 0.06)

    def test_render_learning_persists_aggregate_prompt_video_and_qc_signals(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".learning_profile.json"
            profile = record_render(
                path,
                "Use warm lighting and subtle zoom around the speaker",
                {
                    "frames_analyzed": 8,
                    "face_detected_frames": 6,
                    "exposure": {"low_light_sample_count": 2, "overexposed_sample_count": 1},
                },
                {"status": "passed", "media_health": {"warnings": ["Audio peak is high"]}},
                {"smart_zoom_strength": 0.05, "silence_threshold_db": -38, "silence_min_seconds": 5},
            )
            self.assertEqual(profile["renders"], 1)
            self.assertEqual(profile["prompt_preferences"]["warm"], 1)
            self.assertEqual(profile["video_patterns"]["low_light"], 2)
            self.assertEqual(profile["quality_trends"]["qc_passes"], 1)
            self.assertTrue(path.is_file())
            self.assertNotIn("speaker", path.read_text(encoding="utf-8"))

    def test_feedback_is_persisted_and_invalid_rating_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            profile = record_feedback(path, "better", "Less zoom please")
            self.assertEqual(profile["feedback"]["better"], 1)
            self.assertIn("0 renders", profile_summary(profile))
            with self.assertRaises(ValueError):
                record_feedback(path, "excellent")

    def test_profile_corruption_falls_back_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_profile(path)["renders"], 0)


if __name__ == "__main__":
    unittest.main()
