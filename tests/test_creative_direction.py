import unittest

from studio_core.creative_direction import interpret_creative_direction, build_drawtext_filter

class CreativeDirectionTests(unittest.TestCase):
    def test_simple_quoted_text_overlay_is_supported(self):
        plan = interpret_creative_direction('Add the text "LEVEL UP" at the top.')
        self.assertEqual(plan["status"], "supported")
        self.assertEqual(plan["effect"]["text"], "LEVEL UP")
        self.assertEqual(plan["effect"]["position"], "top")
        self.assertIn("drawtext=", build_drawtext_filter(plan["effect"]))

    def test_neck_orbit_uses_face_tracked_2d_approximation(self):
        plan = interpret_creative_direction('Make "LEVEL UP" orbit around the neck and follow the person.')
        self.assertEqual(plan["status"], "supported_2d_approximation")
        self.assertEqual(plan["effect"]["type"], "neck_orbit_2d")
        self.assertIn("does not provide true 3D", plan["note"])

    def test_missing_exact_words_requests_clarification(self):
        plan = interpret_creative_direction("Add a stylish title at the top")
        self.assertEqual(plan["status"], "needs_clarification")

    def test_drawtext_rejects_unknown_position(self):
        self.assertEqual(build_drawtext_filter({"text": "hello", "position": "outside"}), "")

if __name__ == "__main__":
    unittest.main()