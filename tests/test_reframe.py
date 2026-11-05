import unittest

from studio_core.reframe import build_face_center_expression


class FaceReframeTests(unittest.TestCase):
    def test_no_face_uses_center_fallback(self):
        expression = build_face_center_expression({"samples": []}, [], 0.5)
        self.assertEqual(expression, "0.50000")

    def test_tracks_and_interpolates_detected_face(self):
        analysis = {"samples": [
            {"time_seconds": 0.0, "face_center_x": 0.3},
            {"time_seconds": 2.0, "face_center_x": 0.7},
        ]}
        expression = build_face_center_expression(analysis, [])
        self.assertIn("0.30000", expression)
        self.assertIn("0.70000", expression)
        self.assertIn("lt(t", expression)

    def test_remaps_keyframes_after_removed_silence(self):
        analysis = {"samples": [
            {"time_seconds": 1.0, "face_center_x": 0.4},
            {"time_seconds": 5.0, "face_center_x": 0.6},
        ]}
        expression = build_face_center_expression(analysis, [[2.0, 4.0]])
        self.assertIn("2.000", expression)


if __name__ == "__main__":
    unittest.main()