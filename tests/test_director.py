import unittest

from studio_core.director import _validate_plan, create_director_plan


class DirectorTests(unittest.TestCase):
    def test_validation_discards_out_of_range_indexes(self):
        plan = _validate_plan({
            "summary": "test",
            "hook_segment_indexes": [0, 9, -1],
            "cut_suggestions": [{"segment_indexes": [1, 99], "confidence": 0.9}],
        }, 2)
        self.assertEqual(plan["hook_segment_indexes"], [0])
        self.assertEqual(plan["cut_suggestions"][0]["segment_indexes"], [1])
        self.assertTrue(plan["cut_suggestions"][0]["approval_required"])
        self.assertFalse(plan["safety"]["automatic_speech_deletion"])

    def test_fallback_when_no_api_key(self):
        rows = [{"start": 0, "end": 2, "text": "This is a short sample transcript."}]
        result = create_director_plan(rows)
        self.assertIn(result["status"], {"ai_review", "fallback_review"})
        self.assertFalse(result["safety"]["automatic_speech_deletion"])


    def test_validation_handles_malformed_optional_sections(self):
        plan = _validate_plan({
            "hook_segment_indexes": "not-a-list",
            "sections": [None, {"start_segment": 0, "end_segment": 1}],
            "take_decisions": [None, {"segment_indexes": [0], "confidence": float("nan")}],
            "cut_suggestions": [None, {"segment_indexes": [1], "confidence": "not-a-number"}],
            "broll_suggestions": [None, {"segment_index": 0}],
            "caption_emphasis": [None, {"segment_index": 0, "words": ["focus"]}],
        }, 2)
        self.assertEqual(plan["hook_segment_indexes"], [])
        self.assertEqual(plan["take_decisions"][0]["confidence"], 0.0)
        self.assertEqual(plan["cut_suggestions"][0]["confidence"], 0.0)
        self.assertEqual(len(plan["sections"]), 1)
        self.assertEqual(len(plan["broll_suggestions"]), 1)
        self.assertEqual(len(plan["caption_emphasis"]), 1)

    def test_validation_rejects_non_object_plan(self):
        with self.assertRaises(ValueError):
            _validate_plan([], 1)


if __name__ == "__main__":
    unittest.main()
