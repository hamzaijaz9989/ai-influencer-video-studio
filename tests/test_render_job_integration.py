import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio import render_job


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class RenderJobIntegrationTests(unittest.TestCase):
    def test_complete_render_job_with_synthetic_talking_head_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "OUTPUT"
            work = root / "WORK"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=2160x3840:rate=15:duration=1.6", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000:duration=1.6",
                "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "pools=1:frame-threads=1",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)
            ], check=True)
            transcript = ([{
                "start": 0.1, "end": 1.4,
                "text": "This is a complete synthetic test of the video editing pipeline.",
                "words": []
            }], "en", 0.99)
            visual = {
                "preferred_horizontal_center": 0.5,
                "samples": [],
                "status": "complete",
            }
            with patch("studio.transcribe", return_value=transcript), \
                 patch("studio.analyze_video", return_value=visual), \
                 patch("studio.detect_long_silences", return_value=[]):
                final = render_job(source, output, work, False)
            self.assertTrue(final.is_file())
            self.assertGreater(final.stat().st_size, 0)
            self.assertTrue((final.parent / "quality_report.json").is_file())
            self.assertTrue((final.parent / "director_plan.json").is_file())
            self.assertFalse(work.exists() and any(work.iterdir()))


if __name__ == "__main__":
    unittest.main()
