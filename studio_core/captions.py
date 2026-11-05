"""Styled ASS captions with director-selected keyword emphasis."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import __name__ as _package_name  # keep package import explicit


def _remap(value: float, cuts: list[list[float]]) -> float | None:
    removed = 0.0
    for start, end in cuts:
        if value >= end:
            removed += end - start
        elif start < value < end:
            return None
    return max(0.0, value - removed)


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, centiseconds = divmod(centiseconds, 360000)
    minutes, centiseconds = divmod(centiseconds, 6000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"


def build_ass(
    segments: list[dict[str, Any]],
    cuts: list[list[float]],
    destination: Path,
    director_plan: dict[str, Any] | None = None,
) -> int:
    """Write readable white captions with selected yellow keywords."""
    emphasis: dict[int, set[str]] = {}
    for item in (director_plan or {}).get("caption_emphasis", []):
        index = item.get("segment_index")
        if isinstance(index, int) and not isinstance(index, bool):
            emphasis.setdefault(index, set()).update(
                str(word).casefold() for word in item.get("words", [])
            )

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,58,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,1,5,1,2,90,90,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for index, segment in enumerate(segments):
        midpoint = (float(segment["start"]) + float(segment["end"])) / 2
        if any(start <= midpoint <= end for start, end in cuts):
            continue
        start = _remap(float(segment["start"]), cuts)
        end = _remap(float(segment["end"]), cuts)
        if start is None or end is None or end <= start:
            continue
        selected = emphasis.get(index, set())
        parts = re.findall(r"\w+|[^\w]+", str(segment.get("text", "")), flags=re.UNICODE)
        styled = []
        for part in parts:
            escaped = part.replace("{", "\\{").replace("}", "\\}")
            if part.casefold() in selected and re.search(r"\w", part):
                styled.append("{\\c&H0000FFFF&}" + escaped + "{\\c&H00FFFFFF&}")
            else:
                styled.append(escaped)
        text = "".join(styled).replace("\n", "\\N")
        rows.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
        )
    destination.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)
