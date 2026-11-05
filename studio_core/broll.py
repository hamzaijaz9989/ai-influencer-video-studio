"""Build a reviewable B-roll shot list from validated AI Director suggestions."""
from __future__ import annotations

from typing import Any


def _edited_time(value: float, cuts: list[list[float]]) -> float | None:
    removed = 0.0
    for start, end in cuts:
        if start < value < end:
            return None
        if value >= end:
            removed += end - start
    return max(0.0, value - removed)


def build_broll_shotlist(
    segments: list[dict[str, Any]],
    director_plan: dict[str, Any],
    cuts: list[list[float]],
) -> list[dict[str, Any]]:
    """Return safe B-roll requests; never downloads or inserts unlicensed media."""
    shots = []
    suggestions = director_plan.get("broll_suggestions", [])
    if not isinstance(suggestions, list):
        return shots
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        index = suggestion.get("segment_index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(segments):
            continue
        segment = segments[index]
        try:
            source_start = float(segment["start"])
            source_end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        # Do not stretch a B-roll overlay across unrelated footage after a cut.
        if any(source_start < cut_end and source_end > cut_start for cut_start, cut_end in cuts):
            continue
        start = _edited_time(source_start, cuts)
        end = _edited_time(source_end, cuts)
        idea = str(suggestion.get("visual_idea", "")).strip()[:240]
        if start is None or end is None or end <= start or not idea:
            continue
        shots.append({
            "segment_index": index,
            "source_start_seconds": round(source_start, 3),
            "source_end_seconds": round(source_end, 3),
            "edited_start_seconds": round(start, 3),
            "edited_end_seconds": round(end, 3),
            "visual_idea": idea,
            "reason": str(suggestion.get("reason", ""))[:400],
            "asset_status": "needs_licensed_or_user_supplied_media",
            "inserted_automatically": False,
        })
    return shots
