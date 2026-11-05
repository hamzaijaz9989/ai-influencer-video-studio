"""Conservative editorial analysis. Suggestions are never applied automatically."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def review_repeated_lines(segments: list[dict[str, Any]], threshold: float = 0.82) -> list[dict[str, Any]]:
    """Find likely repeated/retaken lines for human/AI-director review.

    Only compares reasonably substantial transcript segments. It does not decide
    which take is better and does not create cuts.
    """
    candidates: list[dict[str, Any]] = []
    usable = []
    for index, segment in enumerate(segments):
        text = normalize(str(segment.get("text", "")))
        if len(text.split()) >= 4:
            usable.append((index, segment, text))
    for pos, (i, left, a) in enumerate(usable):
        for j, right, b in usable[pos + 1:]:
            if float(right.get("start", 0)) - float(left.get("end", 0)) > 90:
                break
            score = SequenceMatcher(None, a, b).ratio()
            if score >= threshold:
                candidates.append({
                    "first_segment_index": i,
                    "second_segment_index": j,
                    "first_time": [left.get("start"), left.get("end")],
                    "second_time": [right.get("start"), right.get("end")],
                    "similarity": round(score, 3),
                    "first_text": left.get("text", ""),
                    "second_text": right.get("text", ""),
                    "decision": "REVIEW_REQUIRED",
                    "reason": "Similar wording may indicate a retake, repetition, or intentional emphasis.",
                })
    return candidates


def build_editorial_review(segments: list[dict[str, Any]], language: str | None = None) -> dict[str, Any]:
    return {
        "status": "suggestions_only",
        "language": language,
        "repeated_line_candidates": review_repeated_lines(segments),
        "policy": "No speech is removed based on transcript similarity alone. Review candidates before cutting.",
    }
