"""Conservative, local self-improvement from prompts, source-video analysis and render outcomes.

This is preference/settings adaptation, not model training. It stores aggregate signals only,
never source media or transcripts, and all learned controls remain within safe bounds.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_VERSION = 1
DEFAULT_PROFILE: dict[str, Any] = {
    "version": PROFILE_VERSION,
    "created_at": None,
    "updated_at": None,
    "renders": 0,
    "feedback": {"better": 0, "same": 0, "worse": 0},
    "prompt_preferences": {},
    "video_patterns": {"low_light": 0, "overexposed": 0, "face_tracking_success": 0, "face_tracking_total": 0},
    "quality_trends": {"qc_passes": 0, "qc_failures": 0, "warnings": {}},
    "learned_adjustments": {},
}

SAFE_BOUNDS = {
    "smart_zoom_strength": (0.02, 0.09),
}


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def load_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict) and stored.get("version") == PROFILE_VERSION:
                for key in profile:
                    if key in stored and isinstance(stored[key], type(profile[key])):
                        profile[key] = stored[key]
        except (OSError, ValueError, TypeError):
            # Keep the last usable defaults; never block editing due to learning data.
            pass
    return profile


def recommend_revisions(base: dict[str, Any], visual: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Adapt only conservative numeric controls using current footage + accumulated patterns."""
    result = dict(base)
    exposure = visual.get("exposure", {}) if isinstance(visual, dict) else {}
    total = max(1, int(visual.get("frames_analyzed", 0) or 0))
    low_ratio = float(exposure.get("low_light_sample_count", 0) or 0) / total
    bright_ratio = float(exposure.get("overexposed_sample_count", 0) or 0) / total
    # Avoid aggressive punch-ins when face tracking is sparse or the user has disliked edits.
    tracking = float(visual.get("face_detection_ratio", 0.0) or 0.0)
    feedback = profile.get("feedback", {})
    dislikes = int(feedback.get("worse", 0) or 0)
    likes = int(feedback.get("better", 0) or 0)
    zoom = float(result.get("smart_zoom_strength", 0.06))
    if tracking < 0.25:
        zoom *= 0.65
    elif tracking > 0.70:
        zoom *= 1.05
    if dislikes > likes:
        zoom *= 0.85
    # Learn broad visual style preferences from prior creative prompts.
    preferences = profile.get("prompt_preferences", {})
    subtle = int(preferences.get("subtle", 0)) + int(preferences.get("smooth", 0))
    dynamic = int(preferences.get("dynamic", 0)) + int(preferences.get("bold", 0))
    if subtle > dynamic:
        zoom *= 0.95
    elif dynamic > subtle:
        zoom *= 1.02
    result["smart_zoom_strength"] = round(max(0.02, min(0.09, zoom)), 3)
    # Preserve user-defined silence settings; learning never changes speech cuts.
    return result


def record_render(path: Path, prompt: str, visual: dict[str, Any], qc: dict[str, Any],
                  applied_revisions: dict[str, Any]) -> dict[str, Any]:
    profile = load_profile(path)
    now = datetime.now(timezone.utc).isoformat()
    if not profile.get("created_at"):
        profile["created_at"] = now
    profile["updated_at"] = now
    profile["renders"] = int(profile.get("renders", 0)) + 1

    # Store broad style terms, not raw prompts or personal/video content.
    tokens = re.findall(r"[a-z]{3,20}", (prompt or "").lower())
    style_terms = {"warm", "cool", "cinematic", "subtle", "bold", "minimal", "clean", "smooth", "dynamic", "slow", "fast", "zoom", "closeup", "close", "wide", "orbit", "glow", "fade", "animated", "captions", "caption", "lighting", "color", "contrast", "sharp", "soft", "stabilized", "stabilization", "vertical", "horizontal", "tracking", "depth", "3d", "text"}
    preferences = profile.setdefault("prompt_preferences", {})
    for token in set(tokens) & style_terms:
        preferences[token] = min(100, int(preferences.get(token, 0)) + 1)

    patterns = profile.setdefault("video_patterns", {})
    exposure = visual.get("exposure", {}) if isinstance(visual, dict) else {}
    patterns["low_light"] = int(patterns.get("low_light", 0)) + int(exposure.get("low_light_sample_count", 0) or 0)
    patterns["overexposed"] = int(patterns.get("overexposed", 0)) + int(exposure.get("overexposed_sample_count", 0) or 0)
    patterns["face_tracking_success"] = int(patterns.get("face_tracking_success", 0)) + int(visual.get("face_detected_frames", 0) or 0)
    patterns["face_tracking_total"] = int(patterns.get("face_tracking_total", 0)) + int(visual.get("frames_analyzed", 0) or 0)

    trends = profile.setdefault("quality_trends", {})
    if qc.get("status") == "passed":
        trends["qc_passes"] = int(trends.get("qc_passes", 0)) + 1
    else:
        trends["qc_failures"] = int(trends.get("qc_failures", 0)) + 1
    warnings = (qc.get("media_health") or {}).get("warnings", [])
    warning_counts = trends.setdefault("warnings", {})
    for warning in warnings:
        key = str(warning)[:160]
        warning_counts[key] = min(100, int(warning_counts.get(key, 0)) + 1)

    profile["learned_adjustments"] = {
        key: applied_revisions[key] for key in SAFE_BOUNDS if key in applied_revisions
    }
    _atomic_write(path, profile)
    return profile


def record_feedback(path: Path, rating: str, note: str = "") -> dict[str, Any]:
    if rating not in {"better", "same", "worse"}:
        raise ValueError("Feedback must be better, same or worse.")
    profile = load_profile(path)
    feedback = profile.setdefault("feedback", {})
    feedback[rating] = int(feedback.get(rating, 0)) + 1
    profile["last_feedback"] = {
        "rating": rating,
        "note": re.sub(r"[^a-zA-Z0-9 .,!?'-]", "", note)[:240],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    profile["updated_at"] = profile["last_feedback"]["updated_at"]
    _atomic_write(path, profile)
    return profile


def profile_summary(profile: dict[str, Any]) -> str:
    feedback = profile.get("feedback", {})
    patterns = profile.get("video_patterns", {})
    return (
        f"**Learning history:** {profile.get('renders', 0)} renders · "
        f"{feedback.get('better', 0)} positive / {feedback.get('same', 0)} neutral / "
        f"{feedback.get('worse', 0)} negative feedback. "
        f"Tracked {patterns.get('face_tracking_total', 0)} sampled frames. "
        "Learning is local, incremental and bounded."
    )
