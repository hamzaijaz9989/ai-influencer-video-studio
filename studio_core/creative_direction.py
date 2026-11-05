"""Interpret a deliberately small, safe subset of creator directions."""
from __future__ import annotations
import re
from typing import Any

POSITIONS = {
    "top": ("(w-text_w)/2", "h*0.18"),
    "center": ("(w-text_w)/2", "(h-text_h)/2"),
    "bottom": ("(w-text_w)/2", "h*0.78"),
}

def interpret_creative_direction(prompt: str) -> dict[str, Any]:
    """Parse simple title-card requests; clearly reject unsupported tracking effects."""
    raw = str(prompt or "").strip()[:5000]
    if not raw:
        return {"status": "empty", "prompt": ""}
    lower = raw.casefold()
    match = re.search(r"""[\'"]([^\'"]{1,80})[\'"]""", raw)
    orbit_requested = any(term in lower for term in ("orbit", "revolve", "around the neck", "wrap around"))
    tracking_requested = any(term in lower for term in ("follow their movement", "track the person", "follow the person"))
    if orbit_requested or tracking_requested:
        if match:
            return {
                "status": "supported_2d_approximation", "prompt": raw,
                "effect": {"type": "neck_orbit_2d", "text": match.group(1).strip()},
                "note": "A 2D face-tracked orbit approximation will be rendered. It does not provide true 3D perspective, body segmentation or behind-the-neck occlusion.",
            }
        return {"status": "needs_clarification", "prompt": raw, "note": "Please put the exact words to orbit around the subject in quotation marks."}
    if not match:
        return {"status": "needs_clarification", "prompt": raw, "note": "For a text overlay, put the exact words in quotation marks."}
    text = match.group(1).strip()
    position = next((name for name in POSITIONS if re.search(rf"\b{name}\b", lower)), "center")
    if not any(term in lower for term in ("text", "title", "words", "caption", "write", "show")):
        return {"status": "needs_clarification", "prompt": raw, "note": "Please describe how the quoted words should appear."}
    return {
        "status": "supported", "prompt": raw,
        "effect": {"type": "text_overlay", "text": text, "position": position, "animation": "fade_in"},
        "note": "A simple text overlay will be rendered. Subject tracking and 3D depth effects are not included.",
    }

def _escape_drawtext(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")

def build_drawtext_filter(effect: dict[str, Any]) -> str:
    """Build a restrained, animated title overlay from validated fields only."""
    text = str(effect.get("text", ""))[:80]
    position = effect.get("position", "center")
    if not text or position not in POSITIONS:
        return ""
    x, y = POSITIONS[position]
    safe_text = _escape_drawtext(text)
    return (
        "drawtext=text=\'" + safe_text + "\':"
        "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "fontsize=82:fontcolor=white:borderw=5:bordercolor=black@0.75:"
        "x=" + x + ":y=" + y + ":alpha=\'min(1,t/0.35)\'"
    )

def apply_neck_orbit(video_path: str, effect: dict[str, Any]) -> None:
    """Render a tracked 2D orbit approximation; not 3D depth or occlusion."""
    import math
    import os
    import subprocess
    import tempfile
    import cv2
    from pathlib import Path

    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("Could not open rendered video for creative overlay.")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        cap.release()
        raise RuntimeError("OpenCV face detector could not be loaded.")
    text = str(effect.get("text", ""))[:60]
    if not text:
        cap.release()
        raise ValueError("Orbit text cannot be empty.")
    fd, silent_path = tempfile.mkstemp(suffix="_orbit.mp4", dir=str(path.parent))
    os.close(fd)
    fd, mux_path = tempfile.mkstemp(suffix="_mux.mp4", dir=str(path.parent))
    os.close(fd)
    writer = cv2.VideoWriter(silent_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not initialize video writer for creative overlay.")
    anchor = None
    last_face = None
    processed = 0
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = max(0.55, min(1.1, width / 1100.0))
    thickness = max(1, int(width / 700))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = detector.detectMultiScale(
                gray, scaleFactor=1.12, minNeighbors=5,
                minSize=(max(40, width // 18), max(40, height // 35))
            )
            if len(detections):
                if last_face is None:
                    chosen = max(detections, key=lambda box: box[2] * box[3])
                else:
                    chosen = min(detections, key=lambda box:
                        (box[0] + box[2] / 2 - last_face[0]) ** 2
                        + (box[1] + box[3] / 2 - last_face[1]) ** 2)
                x, y, fw, fh = [int(v) for v in chosen]
                target = (x + fw / 2.0, y + fh * 1.18, fw, fh)
                anchor = target if anchor is None else tuple(
                    0.72 * a + 0.28 * b for a, b in zip(anchor, target)
                )
                last_face = (target[0], target[1])
            if anchor is not None:
                cx, cy, fw, fh = anchor
                angle = (processed / max(fps, 1.0)) * 2.2
                px = int(cx + math.cos(angle) * max(48, fw * 0.72))
                py = int(cy + math.sin(angle) * max(22, fh * 0.24))
                (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
                cv2.putText(frame, text, (px - tw // 2, py + th // 2),
                            font, scale, (0, 0, 0), thickness + 5, cv2.LINE_AA)
                cv2.putText(frame, text, (px - tw // 2, py + th // 2),
                            font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
            writer.write(frame)
            processed += 1
    finally:
        cap.release()
        writer.release()
    if processed == 0:
        for temp in (silent_path, mux_path):
            try: os.unlink(temp)
            except OSError: pass
        raise RuntimeError("No frames were available for creative overlay.")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", silent_path, "-i", str(path),
            "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-shortest", mux_path
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        os.replace(mux_path, path)
    finally:
        for temp in (silent_path, mux_path):
            try: os.unlink(temp)
            except OSError: pass
