"""Lightweight visual analysis for shot-aware framing and editorial QC."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from statistics import median
from typing import Any


def analyze_video(path: Path, sample_fps: float = 0.5, max_width: int = 640) -> dict[str, Any]:
    """Sample frames, detect frontal faces, exposure and abrupt visual changes.

    OpenCV is optional at import time but required when this function is used.
    The analysis is advisory: no identity recognition or emotion inference.
    """
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Install opencv-python-headless to enable visual analysis.") from exc

    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required for visual sampling.")

    with tempfile.TemporaryDirectory(prefix="hk_visual_") as temp:
        pattern = str(Path(temp) / "frame_%06d.jpg")
        fps = max(0.1, min(float(sample_fps), 1.0))
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vf", f"fps={fps},scale='min({max_width},iw)':-2",
             "-q:v", "4", pattern],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        files = sorted(Path(temp).glob("frame_*.jpg"))
        if not files:
            raise RuntimeError("Visual analysis could not extract any frames.")

        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        detector = cv2.CascadeClassifier(cascade_path)
        if detector.empty():
            raise RuntimeError("OpenCV face detector could not be loaded.")

        face_centers: list[float] = []
        samples = []
        previous_hist = None
        scene_changes = []
        for index, frame_path in enumerate(files):
            frame = cv2.imread(str(frame_path))
            if frame is None:
                continue
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_small = cv2.resize(gray, (max(1, width // 2), max(1, height // 2)))
            faces = detector.detectMultiScale(
                gray_small, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
            )
            boxes = []
            for x, y, w, h in faces:
                # Convert half-resolution detector coordinates back to frame space.
                box = [int(x * 2), int(y * 2), int(w * 2), int(h * 2)]
                boxes.append(box)
            if boxes:
                largest = max(boxes, key=lambda b: b[2] * b[3])
                center = (largest[0] + largest[2] / 2) / width
                face_centers.append(float(center))
            brightness = float(gray.mean())
            contrast = float(gray.std())
            hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
            cv2.normalize(hist, hist)
            if previous_hist is not None:
                distance = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                if distance >= 0.48:
                    scene_changes.append(round(index / fps, 2))
            previous_hist = hist
            samples.append({
                "time_seconds": round(index / fps, 2),
                "brightness_mean": round(brightness, 2),
                "contrast_std": round(contrast, 2),
                "face_count": len(boxes),
                "face_boxes": boxes,
            })

    valid_centers = face_centers
    preferred_center = float(median(valid_centers)) if valid_centers else 0.5
    return {
        "status": "complete",
        "method": "opencv_haar_frontal_face_sampled_frames",
        "sample_fps": fps,
        "frames_analyzed": len(samples),
        "face_detected_frames": len(valid_centers),
        "face_detection_ratio": round(len(valid_centers) / max(1, len(samples)), 3),
        "preferred_horizontal_center": round(max(0.05, min(0.95, preferred_center)), 4),
        "scene_change_candidates_seconds": scene_changes[:200],
        "exposure": {
            "mean_brightness": round(sum(x["brightness_mean"] for x in samples) / max(1, len(samples)), 2),
            "mean_contrast": round(sum(x["contrast_std"] for x in samples) / max(1, len(samples)), 2),
            "low_light_sample_count": sum(x["brightness_mean"] < 35 for x in samples),
            "overexposed_sample_count": sum(x["brightness_mean"] > 220 for x in samples),
        },
        "samples": samples,
        "limitations": [
            "Frontal-face detection is approximate and can miss profiles, occlusion or poor lighting.",
            "Face detection does not infer gestures, gaze, identity or emotion.",
            "The suggested crop center is a single-video median, not a shot-by-shot tracker.",
        ],
    }
