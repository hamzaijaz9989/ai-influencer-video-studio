"""Conservative, director-triggered smart punch-in expressions for FFmpeg."""
from __future__ import annotations

from typing import Any


def _remap_time(value: float, cuts: list[list[float]]) -> float | None:
    removed = 0.0
    for start, end in cuts:
        if start < value < end:
            return None
        if value >= end:
            removed += end - start
    return max(0.0, value - removed)


def build_smart_zoom_expression(
    segments: list[dict[str, Any]],
    director_plan: dict[str, Any],
    cuts: list[list[float]],
    strength: float = 0.06,
    padding: float = 0.20,
    ramp_seconds: float = 0.35,
) -> str:
    """Create a subtle 1x-to-punch-in expression for AI-selected hook segments.

    Only validated hook indexes are used. The expression is intended for
    FFmpeg zoompan's in_time variable after the video has been cut/concatenated.
    """
    if not 0.0 <= strength <= 0.15:
        raise ValueError("strength must be between 0 and 0.15")
    if padding < 0 or ramp_seconds <= 0:
        raise ValueError("padding must be non-negative and ramp_seconds positive")

    intervals: list[list[float]] = []
    for index in director_plan.get("hook_segment_indexes", []):
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(segments):
            continue
        segment = segments[index]
        try:
            start = float(segment["start"]) - padding
            end = float(segment["end"]) + padding
        except (KeyError, TypeError, ValueError):
            continue
        mapped_start = _remap_time(max(0.0, start), cuts)
        mapped_end = _remap_time(end, cuts)
        if mapped_start is None or mapped_end is None or mapped_end <= mapped_start:
            continue
        intervals.append([mapped_start, mapped_end])

    if not intervals or strength == 0:
        return "1"

    intervals.sort(key=lambda pair: pair[0])
    merged: list[list[float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    expression = "1"
    for start, end in reversed(merged):
        # Smooth ramp-in and ramp-out avoid a visible snap at the segment edge.
        ramp = min(ramp_seconds, max(0.05, (end - start) / 2))
        progress = (
            f"max(0\\,min(1\\,(in_time-{start:.3f})/{ramp:.3f}"
            f"\\,( {end:.3f}-in_time)/{ramp:.3f}))"
        )
        zoom = f"(1+{strength:.4f}*{progress})"
        expression = (
            f"if(between(in_time\\,{start:.3f}\\,{end:.3f})"
            f"\\,{zoom}\\,{expression})"
        )
    return expression
