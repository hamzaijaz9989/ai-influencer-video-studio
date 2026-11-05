#!/usr/bin/env python3
"""HK AI Video Studio: reusable folder watcher and conservative editing worker."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}


def command(args: list[str], check: bool = True) -> str:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and proc.returncode:
        raise RuntimeError(proc.stdout[-5000:])
    return proc.stdout


def require_tools() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed and available on PATH.")


def probe_video(path: Path) -> dict[str, Any]:
    data = json.loads(command([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height,avg_frame_rate",
        "-of", "json", str(path)
    ]))
    return data


def detect_long_silences(path: Path, duration: float, threshold_db: int = -38, min_seconds: int = 5) -> list[list[float]]:
    output = command([
        "ffmpeg", "-hide_banner", "-i", str(path), "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_seconds}",
        "-f", "null", "-"
    ], check=False)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", output)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", output)]
    intervals = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else duration
        if end - start >= min_seconds:
            intervals.append([max(0.0, start - 0.12), min(duration, end + 0.12)])
    merged: list[list[float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def retained_intervals(duration: float, cuts: list[list[float]]) -> list[list[float]]:
    keep, cursor = [], 0.0
    for start, end in cuts:
        if start > cursor:
            keep.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append([cursor, duration])
    return keep or [[0.0, duration]]


def srt_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def remap_timestamp(value: float, cuts: list[list[float]]) -> float | None:
    removed = 0.0
    for start, end in cuts:
        if value >= end:
            removed += end - start
        elif start < value < end:
            return None
    return max(0.0, value - removed)


def transcribe(audio_path: Path, use_gpu: bool) -> tuple[list[dict[str, Any]], str, float]:
    from faster_whisper import WhisperModel
    model = WhisperModel(
        "small" if use_gpu else "base",
        device="cuda" if use_gpu else "cpu",
        compute_type="float16" if use_gpu else "int8"
    )
    segments_iter, info = model.transcribe(
        str(audio_path), beam_size=5, vad_filter=True, word_timestamps=True
    )
    segments = []
    for segment in segments_iter:
        words = []
        if segment.words:
            words = [
                {"start": float(w.start), "end": float(w.end), "word": w.word}
                for w in segment.words
            ]
        segments.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip(),
            "words": words
        })
    return segments, info.language, float(info.language_probability)


def build_srt(segments: list[dict[str, Any]], cuts: list[list[float]], destination: Path) -> int:
    rows, index = [], 1
    for segment in segments:
        midpoint = (segment["start"] + segment["end"]) / 2
        if any(start <= midpoint <= end for start, end in cuts):
            continue
        start = remap_timestamp(segment["start"], cuts)
        end = remap_timestamp(segment["end"], cuts)
        if start is None or end is None or end <= start:
            continue
        text = segment["text"].replace("--", "—").strip()
        rows.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n")
        index += 1
    destination.write_text("\n".join(rows), encoding="utf-8")
    return len(rows)


def render_job(source: Path, output_root: Path, work_root: Path, use_gpu: bool) -> Path:
    require_tools()
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = output_root / f"{source.stem}_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=False)
    work_dir = work_root / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    metadata = probe_video(source)
    duration = float(metadata["format"]["duration"])
    audio_path = work_dir / "analysis.wav"
    command([
        "ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(audio_path)
    ])

    segments, language, language_probability = transcribe(audio_path, use_gpu)
    (job_dir / "transcript.json").write_text(json.dumps({
        "language": language,
        "language_probability": language_probability,
        "segments": segments
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (job_dir / "transcript.txt").write_text(
        "\n".join(f'[{s["start"]:.2f}-{s["end"]:.2f}] {s["text"]}' for s in segments),
        encoding="utf-8"
    )

    silence_cuts = detect_long_silences(source, duration)
    keep = retained_intervals(duration, silence_cuts)
    caption_count = build_srt(segments, silence_cuts, job_dir / "captions.srt")

    parts = []
    for index, (start, end) in enumerate(keep):
        part = work_dir / f"part_{index:03}.mp4"
        command([
            "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(source), "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-c:a", "aac", "-b:a", "160k",
            "-avoid_negative_ts", "make_zero", str(part)
        ])
        parts.append(part)

    concat_file = work_dir / "concat.txt"
    concat_file.write_text(
        "\n".join("file '" + str(part) + "'" for part in parts), encoding="utf-8"
    )
    joined = work_dir / "joined.mp4"
    command(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i",
             str(concat_file), "-c", "copy", str(joined)])

    final_path = job_dir / "FINAL_REVIEW.mp4"
    srt_path = str(job_dir / "captions.srt").replace("\\", "/").replace(":", "\\:")
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,"
        f"subtitles='{srt_path}':force_style='FontName=DejaVu Sans,"
        "FontSize=17,Bold=1,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=3,"
        "Shadow=1,Alignment=2,MarginV=115,WrapStyle=2'"
    )
    command([
        "ffmpeg", "-y", "-i", str(joined), "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(final_path)
    ])

    qc_probe = json.loads(command([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height",
        "-of", "json", str(final_path)
    ]))
    streams = qc_probe.get("streams", [])
    qc = {
        "source": source.name,
        "output": str(final_path),
        "source_duration_seconds": duration,
        "output_duration_seconds": float(qc_probe["format"]["duration"]),
        "removed_silence_intervals": silence_cuts,
        "transcript_segments": len(segments),
        "caption_cues": caption_count,
        "output_bytes": int(qc_probe["format"]["size"]),
        "streams": streams,
        "audio_stream_present": any(s.get("codec_type") == "audio" for s in streams),
        "limitations": [
            "Repeated takes are not automatically deleted; transcript similarity alone is not safe enough.",
            "No semantic/gesture-aware AI director or automatic B-roll sourcing in this baseline.",
            "Review the rendered video before publishing."
        ]
    }
    (job_dir / "quality_report.json").write_text(
        json.dumps(qc, indent=2), encoding="utf-8"
    )
    shutil.rmtree(work_dir, ignore_errors=True)
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("/content/hk_video_work"))
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    args.input.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        use_gpu = torch.cuda.is_available()
    except Exception:
        use_gpu = False

    processed: set[str] = set()
    print(f"Watching {args.input} | GPU available: {use_gpu}", flush=True)
    while True:
        candidates = sorted(
            [p for p in args.input.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS],
            key=lambda p: p.stat().st_mtime
        )
        for source in candidates:
            key = str(source.resolve())
            if key in processed:
                continue
            # Wait until upload size is stable before opening the file.
            size1 = source.stat().st_size
            time.sleep(3)
            if not source.exists() or source.stat().st_size != size1:
                continue
            print(f"\nNew video detected: {source.name}", flush=True)
            try:
                result = render_job(source, args.output, args.work, use_gpu)
                print(f"Completed: {result}", flush=True)
                processed.add(key)
            except Exception as exc:
                error_path = args.output / f"{source.stem}_FAILED_{datetime.now():%Y%m%d_%H%M%S}.txt"
                error_path.write_text(str(exc), encoding="utf-8")
                print(f"FAILED: {source.name}: {exc}", flush=True)
                processed.add(key)
        if not args.watch:
            break
        time.sleep(max(5, args.poll_seconds))


if __name__ == "__main__":
    main()
