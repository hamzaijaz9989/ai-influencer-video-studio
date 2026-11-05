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
        if int(lines[0].strip()) != number:
            errors.append(f"Cue {number}: cue number should be {number}")
        match = timestamp.match(lines[1].strip())
        if not match:
            errors.append(f"Cue {number}: invalid timestamp")
            continue
        parts = tuple(map(int, match.groups()))
        if any(parts[index] > 59 for index in (1, 2, 5, 6)):
            errors.append(f"Cue {number}: minutes and seconds must be between 00 and 59")
        start, end = ms(parts[:4]), ms(parts[4:])
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



def analyze_media_health(video: Path, duration: float) -> dict[str, Any]:
    """Collect advisory black-frame and audio-peak diagnostics without false-failing edits."""
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-i", str(video),
        "-vf", "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-50dB:d=2",
        "-af", "volumedetect", "-f", "null", "-"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    log = result.stderr
    freeze_starts = [float(x) for x in re.findall(r"freeze_start:\s*([0-9.]+)", log)]
    freeze_ends = [float(x) for x in re.findall(r"freeze_end:\s*([0-9.]+)", log)]
    black_durations = [float(x) for x in re.findall(r"black_duration:([0-9.]+)", log)]
    peak_match = re.search(r"max_volume:\s*(-?(?:[0-9]+(?:\.[0-9]+)?|inf))\s*dB", log)
    peak_db = None
    if peak_match and peak_match.group(1) != "inf":
        peak_db = float(peak_match.group(1))
    black_seconds = round(sum(black_durations), 3)
    black_ratio = round(black_seconds / duration, 4) if duration > 0 else 0.0
    warnings = []
    if black_ratio > 0.08:
        warnings.append("More than 8% of the export is detected as black; review for accidental blank frames.")
    if peak_db is not None and peak_db > -0.5:
        warnings.append("Audio peak is close to digital clipping; listen for distortion.")
    freeze_events = []
    for index, start in enumerate(freeze_starts):
        end = freeze_ends[index] if index < len(freeze_ends) else None
        freeze_events.append({"start_seconds": round(start, 3), "end_seconds": round(end, 3) if end is not None else None})
    if freeze_events:
        warnings.append("Potential frozen video frames detected; review the listed intervals (static shots can be intentional).")
    if result.returncode != 0:
        warnings.append("Media-health diagnostics could not complete.")
    return {
        "black_frame_seconds": black_seconds,
        "black_frame_ratio": black_ratio,
        "audio_peak_db": peak_db,
        "potential_freeze_events": freeze_events,
        "warnings": warnings,
        "diagnostics_completed": result.returncode == 0,
    }


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
    media_health = analyze_media_health(video, duration)
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
        "media_health": media_health,
        "decode_error": decode.stderr[-2000:] if not decode_ok else "",
        "failed_checks": [key for key, value in checks.items() if not value],
    }
