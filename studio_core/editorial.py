"""Conservative editorial analysis. Suggestions are never applied automatically."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _take_signals(segment: dict[str, Any]) -> dict[str, Any]:
    """Estimate transcript-only completeness/readability signals, never delivery quality."""
    text = str(segment.get("text", "")).strip()
    words = re.findall(r"\\b[\\w’'-]+\\b", text)
    duration = max(0.05, float(segment.get("end", 0)) - float(segment.get("start", 0)))
    wpm = len(words) / duration * 60
    normalized = text.lower()
    false_start = bool(re.match(r"^(?:uh+|um+|so+|well+|and+|but+|i mean)\\b", normalized))
    complete_ending = bool(re.search(r"[.!?…][\"'”’)]*$", text))
    pace_plausible = 70 <= wpm <= 230
    score = min(1.0, len(words) / 12) * 0.35
    score += 0.25 if complete_ending else 0.0
    score += 0.20 if pace_plausible else 0.0
    score += 0.20 if not false_start else 0.0
    return {
        "word_count": len(words),
        "duration_seconds": round(duration, 2),
        "estimated_words_per_minute": round(wpm, 1),
        "complete_sentence_punctuation": complete_ending,
        "possible_false_start": false_start,
        "transcript_completeness_score": round(score, 3),
    }


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
                    "first_signals": _take_signals(left),
                    "second_signals": _take_signals(right),
                    "review_first_segment_index": (
                        i if _take_signals(left)["transcript_completeness_score"] >= _take_signals(right)["transcript_completeness_score"] + 0.15
                        else j if _take_signals(right)["transcript_completeness_score"] >= _take_signals(left)["transcript_completeness_score"] + 0.15
                        else None
                    ),
                    "decision": "REVIEW_REQUIRED",
                    "reason": "Similar wording may indicate a retake, repetition, or intentional emphasis.",
                })
    return candidates


def build_editorial_review(segments: list[dict[str, Any]], language: str | None = None) -> dict[str, Any]:
    return {
        "status": "suggestions_only",
        "language": language,
        "repeated_line_candidates": review_repeated_lines(segments),
        "policy": "No speech is removed based on transcript similarity alone. Transcript signals can prioritize review but cannot assess vocal delivery, facial expression, or factual accuracy.",
    }
