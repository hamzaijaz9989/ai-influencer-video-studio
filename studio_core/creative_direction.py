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
    if any(term in lower for term in ("orbit", "revolve", "around the neck", "wrap around", "follow their movement", "track the person", "behind the person", "in front of the person")):
        return {
            "status": "needs_advanced_tracking", "prompt": raw,
            "requested_effect": "subject_tracked_3d_orbit",
            "note": "This request needs subject/neck tracking, perspective animation and foreground occlusion. It is saved for the project but not rendered as a fake flat overlay.",
        }
    match = re.search(r"""[\'"]([^\'"]{1,80})[\'"]""", raw)
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