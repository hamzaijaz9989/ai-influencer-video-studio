import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio_core.broll_assets import build_broll_filter
from studio_core.captions import build_ass
from studio_core.reframe import build_face_center_expression
from studio_core.smart_zoom import build_smart_zoom_expression


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class FullRenderGraphIntegrationTests(unittest.TestCase):
    def test_crop_zoom_captions_broll_and_audio_render_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            broll = root / "shot_0.mp4"
            captions = root / "captions.ass"
            output = root / "final.mp4"

            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=red:s=360x640:r=30:d=2", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000:duration=2",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(source)
            ], check=True)
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=green:s=180x320:r=24:d=0.6", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(broll)
            ], check=True)

            segments = [{"start": 0.2, "end": 1.4, "text": "This is a test caption"}]
            plan = {"hook_segment_indexes": [0], "caption_emphasis": [
                {"segment_index": 0, "words": ["test"]}
            ]}
            build_ass(segments, [], captions, plan)
            face_expression = build_face_center_expression({
                "samples": [
                    {"time_seconds": 0.0, "face_center_x": 0.45},
                    {"time_seconds": 1.0, "face_center_x": 0.55},
                ]
            }, [])
            zoom_expression = build_smart_zoom_expression(segments, plan, [], strength=0.04)

            ass_path = str(captions).replace("\\\\", "/").replace(":", "\\\\:")
            base_filter = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920:x='max(0,min(iw-ow,iw*({face_expression})-ow/2))':y=0,setsar=1,"
                f"zoompan=z='{zoom_expression}':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,"
                f"subtitles='{ass_path}'"
            )
            assets = [{
                "asset_path": str(broll),
                "edited_start_seconds": 0.8,
                "edited_end_seconds": 1.4,
            }]
            overlay_graph, final_label = build_broll_filter("base", assets, 1)
            graph = f"[0:v]{base_filter}[base];{overlay_graph};[{final_label}]null[outv]"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-i", str(source),
                "-stream_loop", "-1", "-i", str(broll),
                "-filter_complex", graph, "-map", "[outv]", "-map", "0:a:0?",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-shortest", str(output)
            ], check=True)

            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height", "-of", "json", str(output)
            ], check=True, capture_output=True, text=True)
            import json
            streams = json.loads(probe.stdout)["streams"]
            video = next(s for s in streams if s["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (1080, 1920))
            self.assertTrue(any(s["codec_type"] == "audio" for s in streams))
            decode = subprocess.run([
                "ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"
            ], capture_output=True, text=True)
            self.assertEqual(decode.returncode, 0, decode.stderr)


if __name__ == "__main__":
    unittest.main()
