import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from studio_core.qc import analyze_media_health


class MediaHealthTests(unittest.TestCase):
    @patch("studio_core.qc.subprocess.run")
    def test_reports_black_frames_and_audio_peak(self, run):
        run.return_value = Mock(
            returncode=0,
            stdout="",
            stderr=(
                "[blackdetect] black_duration:2.000\n"
                "[Parsed_volumedetect] max_volume: -0.2 dB\n"
            ),
        )
        result = analyze_media_health(Path("sample.mp4"), 10.0)
        self.assertEqual(result["black_frame_seconds"], 2.0)
        self.assertEqual(result["black_frame_ratio"], 0.2)
        self.assertEqual(result["audio_peak_db"], -0.2)
        self.assertEqual(len(result["warnings"]), 2)

    @patch("studio_core.qc.subprocess.run")
    def test_missing_peak_is_not_invented(self, run):
        run.return_value = Mock(returncode=0, stdout="", stderr="")
        result = analyze_media_health(Path("sample.mp4"), 10.0)
        self.assertIsNone(result["audio_peak_db"])
        self.assertEqual(result["warnings"], [])

    @patch("studio_core.qc.subprocess.run")
    def test_diagnostic_failure_is_advisory(self, run):
        run.return_value = Mock(returncode=1, stdout="", stderr="ffmpeg error")
        result = analyze_media_health(Path("sample.mp4"), 10.0)
        self.assertFalse(result["diagnostics_completed"])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
