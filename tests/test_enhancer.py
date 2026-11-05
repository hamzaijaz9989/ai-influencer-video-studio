import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio_core.enhancer import build_enhancement_filter, enhance_video


class UniversalEnhancerTests(unittest.TestCase):
    def test_all_strengths_build_valid_filter_strings(self):
        for strength in ("light", "balanced", "strong"):
            with self.subTest(strength=strength):
                value = build_enhancement_filter(strength)
                self.assertIn("eq=", value)
                self.assertIn("unsharp=", value)
                self.assertIn("hqdn3d=", value)
                self.assertIn("format=yuv420p", value)

    def test_denoise_can_be_disabled(self):
        self.assertNotIn("hqdn3d=", build_enhancement_filter("light", denoise=False))

    def test_invalid_strength_is_rejected(self):
        with self.assertRaises(ValueError):
            build_enhancement_filter("extreme")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_enhance_synthetic_video_preserves_dimensions_and_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            output = root / "enhanced.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=320x240:rate=24:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(source)
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            enhance_video(source, output, strength="light")
            self.assertTrue(output.is_file())
            self.assertTrue(source.is_file())
            self.assertGreater(output.stat().st_size, 0)
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries",
                "stream=width,height,avg_frame_rate,codec_type",
                "-of", "json", str(output)
            ], check=True, capture_output=True, text=True)
            import json
            streams = json.loads(probe.stdout)["streams"]
            video = next(item for item in streams if item["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (320, 240))
            self.assertEqual(video["avg_frame_rate"], "24/1")
            self.assertTrue(any(item["codec_type"] == "audio" for item in streams))

    def test_original_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.mp4"
            source.write_bytes(b"not a video")
            with self.assertRaises(ValueError):
                enhance_video(source, source)


if __name__ == "__main__":
    unittest.main()
