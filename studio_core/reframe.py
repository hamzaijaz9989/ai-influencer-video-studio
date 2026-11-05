"""Conservative time-varying face-aware crop expressions for FFmpeg."""
from __future__ import annotations

from statistics import median
from typing import Any


def _remap_time(value: float, cuts: list[list[float]]) -> float | None:
    removed = 0.0
    for start, end in cuts:
        if start < value < end:
            return None
        if value >= end:
            removed += end - start
    return max(0.0, value - removed)


def build_face_center_expression(
    visual_analysis: dict[str, Any], cuts: list[list[float]], fallback: float = 0.5
) -> str:
    """Return a smoothed, linearly interpolated normalized face-center expression.

    The returned expression uses FFmpeg crop-filter time `t`; it is safe to use
    as the normalized horizontal center before converting to crop pixels.
    """
    points: list[tuple[float, float]] = []
    for sample in visual_analysis.get("samples", []):
        center = sample.get("face_center_x")
        timestamp = sample.get("time_seconds")
        if not isinstance(center, (int, float)) or not isinstance(timestamp, (int, float)):
            continue
        mapped = _remap_time(float(timestamp), cuts)
        if mapped is not None:
            points.append((mapped, max(0.05, min(0.95, float(center)))))
    if not points:
        return f"{max(0.05, min(0.95, float(fallback))):.5f}"
    points.sort(key=lambda item: item[0])
    # Median smoothing suppresses one-frame detector jumps without hiding movement.
    smoothed = []
    for index, (timestamp, _) in enumerate(points):
        window = [value for _, value in points[max(0, index - 1):index + 2]]
        smoothed_value = float(median(window)) if len(window) == 3 else points[index][1]
        smoothed.append((timestamp, smoothed_value))
    if len(smoothed) == 1:
        return f"{smoothed[0][1]:.5f}"
    expression = f"{smoothed[-1][1]:.5f}"
    for index in range(len(smoothed) - 2, -1, -1):
        t0, c0 = smoothed[index]
        t1, c1 = smoothed[index + 1]
        if t1 <= t0:
            continue
        interpolated = f"({c0:.5f}+({c1-c0:.5f})*(t-{t0:.3f})/{t1-t0:.3f})"
        expression = f"if(lt(t\\,{t1:.3f})\\,{interpolated}\\,{expression})"
    return f"if(lt(t\\,{smoothed[0][0]:.3f})\\,{smoothed[0][1]:.5f}\\,{expression})"
