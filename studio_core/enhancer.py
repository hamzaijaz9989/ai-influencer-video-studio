"""Universal, conservative FFmpeg-based video enhancement."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

STRENGTHS = {
    "light": {"contrast": 1.02, "saturation": 1.03, "brightness": 0.002, "sharp": 0.25, "denoise": 0.6},
    "balanced": {"contrast": 1.04, "saturation": 1.06, "brightness": 0.004, "sharp": 0.40, "denoise": 1.0},
    "strong": {"contrast": 1.07, "saturation": 1.09, "brightness": 0.006, "sharp": 0.55, "denoise": 1.4},
}

def _run(args: list[str]) -> str:
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout[-4000:])
    return result.stdout

def probe_media(source: Path) -> dict[str, Any]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed.")
    data = json.loads(_run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(source)
    ]))
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("The selected file does not contain a video stream.")
    return {"format": data.get("format", {}), "video": video,
            "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", []))}

def build_enhancement_filter(strength: str = "balanced", denoise: bool = True) -> str:
    if strength not in STRENGTHS:
        raise ValueError("Choose light, balanced or strong enhancement.")
    settings = STRENGTHS[strength]
    filters = []
    if denoise:
        amount = settings["denoise"]
        filters.append(f"hqdn3d={amount:.2f}:{amount:.2f}:{amount * 2:.2f}:{amount * 1.5:.2f}")
    filters.extend([
        f"eq=contrast={settings['contrast']:.3f}:saturation={settings['saturation']:.3f}:brightness={settings['brightness']:.3f}",
        f"unsharp=5:5:{settings['sharp']:.2f}:3:3:0.00",
        "format=yuv420p",
    ])
    return ",".join(filters)

def enhance_video(source: Path, destination: Path, strength: str = "balanced",
                  denoise: bool = True) -> Path:
    """Enhance any FFmpeg-readable video while preserving its frame size and frame rate."""
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser()
    if source == destination.resolve() if destination.exists() else source == destination:
        raise ValueError("Enhancement output must be a new file; the original is never overwritten.")
    if source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}:
        raise ValueError("Unsupported video container.")
    metadata = probe_media(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + ".enhancing" + destination.suffix)
    try:
        args = ["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a?"]
        args += ["-vf", build_enhancement_filter(strength, denoise),
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-map_metadata", "0", "-movflags", "+faststart", str(temp)]
        _run(args)
        result = probe_media(temp)
        if result["video"].get("width") != metadata["video"].get("width") or result["video"].get("height") != metadata["video"].get("height"):
            raise RuntimeError("Enhancement unexpectedly changed the source resolution.")
        if metadata["has_audio"] and not result["has_audio"]:
            raise RuntimeError("Enhancement export lost the source audio.")
        temp.replace(destination)
        return destination
    finally:
        if temp.exists():
            temp.unlink()
