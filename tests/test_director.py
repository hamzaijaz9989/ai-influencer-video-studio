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


if __name__ == "__main__":
    unittest.main()
