import unittest

from studio_core.broll import build_broll_shotlist


class BrollShotlistTests(unittest.TestCase):
    def test_valid_suggestion_maps_timing_after_silence(self):
        segments = [{"start": 10.0, "end": 12.0, "text": "topic"}]
        plan = {"broll_suggestions": [
            {"segment_index": 0, "visual_idea": "A city street", "reason": "Context"}
        ]}
        shots = build_broll_shotlist(segments, plan, [[2.0, 5.0]])
        self.assertEqual(shots[0]["edited_start_seconds"], 7.0)
        self.assertFalse(shots[0]["inserted_automatically"])

    def test_ignores_invalid_indexes_and_empty_ideas(self):
        segments = [{"start": 1.0, "end": 2.0}]
        plan = {"broll_suggestions": [
            {"segment_index": True, "visual_idea": "invalid"},
            {"segment_index": 0, "visual_idea": "  "}
        ]}
        self.assertEqual(build_broll_shotlist(segments, plan, []), [])

    def test_ignores_segment_inside_removed_silence(self):
        segments = [{"start": 3.0, "end": 4.0}]
        plan = {"broll_suggestions": [
            {"segment_index": 0, "visual_idea": "A visual"}
        ]}
        self.assertEqual(build_broll_shotlist(segments, plan, [[2.0, 5.0]]), [])


if __name__ == "__main__":
    unittest.main()
