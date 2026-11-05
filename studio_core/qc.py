"""Deterministic export and caption quality checks."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout


def validate_srt(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    errors = []
    previous_end = -1
    cue_count = 0
    timestamp = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$")
    def ms(parts):
        h, m, s, milli = map(int, parts)
        return ((h * 60 + m) * 60 + s) * 1000 + milli
    for number, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            errors.append(f"Cue {number}: malformed block")
            continue
        match = timestamp.match(lines[1].strip())
        if not match:
            errors.append(f"Cue {number}: invalid timestamp")
            continue
        start, end = ms(match.groups()[:4]), ms(match.groups()[4:])
        if end <= start:
            errors.append(f"Cue {number}: end must be after start")
        if start < previous_end:
            errors.append(f"Cue {number}: overlaps previous cue")
        previous_end = end
        if not any(line.strip() for line in lines[2:]):
            errors.append(f"Cue {number}: empty caption")
        cue_count += 1
    if cue_count == 0:
        errors.append("No caption cues found")
    return {"cue_count": cue_count, "valid": not errors, "errors": errors}


def run_export_qc(video: Path, captions: Path, expected_width: int = 1080,
                  expected_height: int = 1920) -> dict[str, Any]:
    probe = json.loads(_run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height,avg_frame_rate",
        "-of", "json", str(video)
    ]))
    streams = probe.get("streams", [])
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    duration = float(probe.get("format", {}).get("duration", 0))
    size = int(probe.get("format", {}).get("size", 0))
    decode = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    decode_ok = decode.returncode == 0 and not decode.stderr.strip()
    srt = validate_srt(captions)
    checks = {
        "file_exists": video.is_file(),
        "file_nonempty": size > 0,
        "video_stream_present": bool(vstreams),
        "audio_stream_present": has_audio,
        "expected_resolution": bool(vstreams and vstreams[0].get("width") == expected_width
                                    and vstreams[0].get("height") == expected_height),
        "positive_duration": duration > 0,
        "full_decode_integrity": decode_ok,
        "captions_valid": srt["valid"],
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "duration_seconds": round(duration, 3),
        "size_bytes": size,
        "streams": streams,
        "captions": srt,
        "decode_error": decode.stderr[-2000:] if not decode_ok else "",
        "failed_checks": [key for key, value in checks.items() if not value],
    }
