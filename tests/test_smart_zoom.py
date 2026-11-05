import unittest

from studio_core.smart_zoom import build_smart_zoom_expression


class SmartZoomTests(unittest.TestCase):
    def test_no_director_hook_keeps_native_scale(self):
        segments = [{"start": 1.0, "end": 3.0, "text": "Hello"}]
        self.assertEqual(build_smart_zoom_expression(segments, {}, []), "1")

    def test_hook_creates_subtle_smooth_zoom(self):
        segments = [{"start": 10.0, "end": 12.0, "text": "Hook"}]
        expression = build_smart_zoom_expression(
            segments, {"hook_segment_indexes": [0]}, []
        )
        self.assertIn("between(in_time", expression)
        self.assertIn("1.0600", expression)
        self.assertIn("min(1", expression)

    def test_removed_silence_remaps_hook_time(self):
        segments = [{"start": 10.0, "end": 12.0, "text": "Hook"}]
        expression = build_smart_zoom_expression(
            segments, {"hook_segment_indexes": [0]}, [[2.0, 5.0]]
        )
        self.assertIn("7.200", expression)

    def test_invalid_hook_indexes_are_ignored(self):
        segments = [{"start": 1.0, "end": 2.0, "text": "Hook"}]
        expression = build_smart_zoom_expression(
            segments, {"hook_segment_indexes": [True, -1, 9]}, []
        )
        self.assertEqual(expression, "1")

    def test_zoom_strength_is_bounded(self):
        with self.assertRaises(ValueError):
            build_smart_zoom_expression([], {}, [], strength=0.5)


if __name__ == "__main__":
    unittest.main()
