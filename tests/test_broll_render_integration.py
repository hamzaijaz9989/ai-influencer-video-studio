import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio_core.broll_assets import build_broll_filter


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class BrollRenderIntegrationTests(unittest.TestCase):
    def test_overlay_renders_inside_requested_window_and_preserves_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.mp4"
            overlay = root / "shot_0.mp4"
            output = root / "out.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=red:s=160x284:r=30:d=3", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(base)
            ], check=True)
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=green:s=160x284:r=24:d=1", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(overlay)
            ], check=True)
            assets = [{
                "asset_path": str(overlay),
                "edited_start_seconds": 1.0,
                "edited_end_seconds": 2.0,
            }]
            graph, final_label = build_broll_filter("base", assets, 1)
            graph = f"[0:v]fps=30,format=yuv420p[base];{graph};[{final_label}]null[outv]"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-i", str(base),
                "-stream_loop", "-1", "-i", str(overlay),
                "-filter_complex", graph, "-map", "[outv]", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)
            ], check=True)
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(output)
            ], check=True, capture_output=True, text=True)
            self.assertAlmostEqual(float(probe.stdout.strip()), 3.0, delta=0.15)

            frame = subprocess.run([
                "ffmpeg", "-v", "error", "-ss", "1.5", "-i", str(output),
                "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo",
                "-pix_fmt", "rgb24", "-"
            ], check=True, capture_output=True).stdout
            red, green, blue = frame[:3]
            self.assertGreater(green, red)
            self.assertGreater(green, blue)


if __name__ == "__main__":
    unittest.main()
