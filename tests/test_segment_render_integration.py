import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio import build_segment_encode_command


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class SegmentRenderIntegrationTests(unittest.TestCase):
    def test_retained_interval_has_requested_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "part.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=160x284:rate=30:duration=8", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000:duration=8",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)
            ], check=True)
            subprocess.run(build_segment_encode_command(source, output, 2.0, 5.0), check=True)
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(output)
            ], check=True, capture_output=True, text=True)
            duration = float(json.loads(probe.stdout)["format"]["duration"])
            self.assertAlmostEqual(duration, 3.0, delta=0.12)


if __name__ == "__main__":
    unittest.main()
