"""Approximate face-following 2D motion effects for portrait exports.

This is not 3D tracking or segmentation. It estimates a neck anchor from a face box.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Any

def sample_face_anchors(video: Path, sample_fps: float = 1.0, max_width: int = 480) -> dict[str, Any]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for face-following effects.") from exc
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if cascade.empty():
        raise RuntimeError("OpenCV frontal-face detector could not be loaded.")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("Could not open rendered video for face tracking.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if fps else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    anchors = []
    sample_step = 1.0 / max(0.2, min(sample_fps, 2.0))
    sample_time = 0.0
    while sample_time < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sample_time * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        scale = min(1.0, max_width / max(1, w))
        small = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda box: box[2] * box[3])
            factor = 1.0 / scale
            center_x = (x + fw / 2) * factor
            neck_y = (y + fh * 1.12) * factor
            anchors.append({"t": round(sample_time, 3), "x": round(center_x, 1), "y": round(neck_y, 1), "face_w": round(fw * factor, 1)})
        sample_time += sample_step
    cap.release()
    return {"duration": duration, "width": width, "height": height, "anchors": anchors, "sample_fps": sample_fps}

def _interpolate_anchors(anchors: list[dict[str, float]], duration: float, width: int, height: int, step: float = 1.0) -> list[dict[str, float]]:
    if not anchors:
        return []
    times = [i * step for i in range(int(duration / step) + 1)]
    out = []
    for t in times:
        before = max((a for a in anchors if a["t"] <= t), key=lambda a: a["t"], default=anchors[0])
        after = min((a for a in anchors if a["t"] >= t), key=lambda a: a["t"], default=anchors[-1])
        if after["t"] == before["t"]:
            ratio = 0.0
        else:
            ratio = (t - before["t"]) / (after["t"] - before["t"])
        out.append({"t": t, "x": before["x"] + (after["x"] - before["x"]) * ratio, "y": before["y"] + (after["y"] - before["y"]) * ratio, "face_w": before["face_w"] + (after["face_w"] - before["face_w"]) * ratio})
    return out

def _piecewise_expression(points: list[dict[str, float]], key: str) -> str:
    if len(points) == 1:
        return f"{points[0][key]:.2f}"
    expression = f"{points[-1][key]:.2f}"
    for left, right in reversed(list(zip(points[:-1], points[1:]))):
        dt = max(0.001, right["t"] - left["t"])
        left_time = left["t"]
        right_time = right["t"]
        segment = f"({left[key]:.2f}+({right[key]-left[key]:.2f})*(t-{left_time:.2f})/{dt:.3f})"
        expression = f"if(lt(t,{right_time:.2f}),{segment},{expression})"
    return expression

def build_orbit_drawtext_filter(text: str, anchors: list[dict[str, float]], duration: float) -> str:
    """Build a horizontal 2D orbit around an estimated neck anchor."""
    if not anchors:
        return ""
    points = _interpolate_anchors(anchors, duration, 1080, 1920)
    cx = _piecewise_expression(points, "x")
    ny = _piecewise_expression(points, "y")
    fw = _piecewise_expression(points, "face_w")
    # A restrained oval path; text remains flat and does not pass behind the subject.
    safe = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")
    return (
        "drawtext=text=\'" + safe + "\':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "fontsize=58:fontcolor=white:borderw=4:bordercolor=black@0.8:"
        "x=\'" + cx + "+max(34," + fw + "*0.72)*cos(2*PI*t/3)-text_w/2\':"
        "y=\'" + ny + "+max(10," + fw + "*0.20)*sin(2*PI*t/3)-text_h/2\':"
        "alpha=\'min(1,t/0.35)\'"
    )

def apply_face_orbit(video: Path, output: Path, text: str) -> dict[str, Any]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)], check=True, capture_output=True, text=True)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    tracking = sample_face_anchors(video)
    anchors = tracking["anchors"]
    ratio = len(anchors) / max(1, int(duration))
    if ratio < 0.2:
        return {"status": "tracking_unavailable", "detected_samples": len(anchors), "note": "Too few frontal face detections for a stable 2D orbit. Original export was kept unchanged."}
    expression = build_orbit_drawtext_filter(text, anchors, duration)
    if not expression:
        return {"status": "tracking_unavailable", "note": "No usable face track was found."}
    subprocess.run(["ffmpeg", "-y", "-i", str(video), "-vf", expression, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)], check=True, capture_output=True, text=True)
    return {"status": "rendered_2d_face_follow", "detected_samples": len(anchors), "detection_ratio": round(ratio, 3), "note": "2D face-following orbit rendered. Text remains in front; no 3D perspective or subject occlusion."}