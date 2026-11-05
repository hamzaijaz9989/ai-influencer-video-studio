import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio_core.qc import analyze_media_health


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class FreezeDetectionIntegrationTests(unittest.TestCase):
    def test_detects_a_sustained_static_frame_as_advisory(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "static.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=blue:s=160x284:r=10:d=3", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(clip)
            ], check=True)
            result = analyze_media_health(clip, 3.0)
            self.assertTrue(result["diagnostics_completed"])
            self.assertTrue(result["potential_freeze_events"])
            self.assertTrue(any("frozen video frames" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
