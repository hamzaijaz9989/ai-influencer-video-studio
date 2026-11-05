"""AI editorial director with a safe, provider-optional review workflow.

The director proposes edits; it never silently removes dialogue. Gemini is optional.
Without an API key, a deterministic fallback still creates a useful editorial brief.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from studio_core.editorial import build_editorial_review


SYSTEM_PROMPT = """You are a careful professional video editor and editorial director.
Review a transcript of a talking-head video. Identify a strong opening hook, likely
retakes/repeated lines, filler or false starts, topic sections, and possible visual
insert opportunities. Preserve the speaker's meaning and factual claims. Do not
invent footage or facts. Do not recommend removing a sentence merely because it
resembles another; compare completeness, clarity and context.

Return ONLY valid JSON with this schema:
{
  "summary": "short editorial summary",
  "hook_segment_indexes": [integer],
  "sections": [{"title":"...", "start_segment":integer, "end_segment":integer}],
  "take_decisions": [{"segment_indexes":[integer], "preferred_segment_index":integer|null,
    "action":"keep_all|prefer_one_for_review", "confidence":0.0,
    "reason":"..."}],
  "cut_suggestions": [{"segment_indexes":[integer], "action":"review_removal",
    "confidence":0.0, "reason":"..."}],
  "broll_suggestions": [{"segment_index":integer,"visual_idea":"...","reason":"..."}],
  "caption_emphasis": [{"segment_index":integer,"words":["..."]}]
}
All indexes must refer to the supplied transcript. If uncertain, return empty arrays.
Every removal is a suggestion requiring human review. Never output a final cut list."""


def _transcript_payload(segments: list[dict[str, Any]]) -> str:
    rows = []
    for index, item in enumerate(segments):
        rows.append({
            "index": index,
            "start": round(float(item.get("start", 0)), 2),
            "end": round(float(item.get("end", 0)), 2),
            "text": str(item.get("text", ""))[:700],
        })
    return json.dumps(rows, ensure_ascii=False)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", cleaned, flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Director response did not contain a JSON object")
    result = json.loads(cleaned[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("Director response must be a JSON object")
    return result


def _validate_plan(plan: dict[str, Any], count: int) -> dict[str, Any]:
    def valid_index(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < count

    hooks = [i for i in plan.get("hook_segment_indexes", []) if valid_index(i)]
    sections = []
    for section in plan.get("sections", []):
        start, end = section.get("start_segment"), section.get("end_segment")
        if valid_index(start) and valid_index(end) and start <= end:
            sections.append({
                "title": str(section.get("title", "Section"))[:120],
                "start_segment": start, "end_segment": end,
            })
    takes = []
    for decision in plan.get("take_decisions", []):
        indexes = [i for i in decision.get("segment_indexes", []) if valid_index(i)]
        preferred = decision.get("preferred_segment_index")
        if indexes:
            takes.append({
                "segment_indexes": indexes,
                "preferred_segment_index": preferred if preferred in indexes else None,
                "action": "prefer_one_for_review" if decision.get("action") == "prefer_one_for_review" else "keep_all",
                "confidence": max(0.0, min(1.0, float(decision.get("confidence", 0)))),
                "reason": str(decision.get("reason", ""))[:500],
            })
    cuts = []
    for suggestion in plan.get("cut_suggestions", []):
        indexes = [i for i in suggestion.get("segment_indexes", []) if valid_index(i)]
        if indexes:
            cuts.append({
                "segment_indexes": indexes, "action": "review_removal",
                "confidence": max(0.0, min(1.0, float(suggestion.get("confidence", 0)))),
                "reason": str(suggestion.get("reason", ""))[:500],
                "approval_required": True,
            })
    broll = []
    for item in plan.get("broll_suggestions", []):
        index = item.get("segment_index")
        if valid_index(index):
            broll.append({
                "segment_index": index,
                "visual_idea": str(item.get("visual_idea", ""))[:240],
                "reason": str(item.get("reason", ""))[:400],
            })
    emphasis = []
    for item in plan.get("caption_emphasis", []):
        index = item.get("segment_index")
        words = item.get("words", [])
        if valid_index(index) and isinstance(words, list):
            emphasis.append({"segment_index": index, "words": [str(w)[:60] for w in words[:8]]})
    return {
        "summary": str(plan.get("summary", ""))[:1000],
        "hook_segment_indexes": hooks[:8],
        "sections": sections[:30],
        "take_decisions": takes[:40],
        "cut_suggestions": cuts[:40],
        "broll_suggestions": broll[:40],
        "caption_emphasis": emphasis[:60],
        "safety": {
            "automatic_speech_deletion": False,
            "approval_required_for_removals": True,
            "index_validation": "passed",
        },
    }


def _gemini_review(segments: list[dict[str, Any]], language: str) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = (
        SYSTEM_PROMPT + "\n\nTranscript language: " + language
        + "\nTranscript with stable indexes:\n" + _transcript_payload(segments)
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"Gemini API returned HTTP {exc.code}: {detail}") from exc
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    return _validate_plan(_extract_json(text), len(segments))


def _fallback_review(segments: list[dict[str, Any]], language: str) -> dict[str, Any]:
    review = build_editorial_review(segments, language)
    return {
        "summary": "Local fallback: transcript structure and repeated-line candidates are prepared. Configure GEMINI_API_KEY for semantic editorial reasoning.",
        "hook_segment_indexes": [],
        "sections": [],
        "take_decisions": [{
            "segment_indexes": [row["first_segment_index"], row["second_segment_index"]],
            "preferred_segment_index": None,
            "action": "keep_all",
            "confidence": 0.0,
            "reason": "Potential retake detected by text similarity only; semantic review is unavailable.",
        } for row in review["repeated_line_candidates"]],
        "cut_suggestions": [],
        "broll_suggestions": [],
        "caption_emphasis": [],
        "safety": {
            "automatic_speech_deletion": False,
            "approval_required_for_removals": True,
            "index_validation": "local_fallback",
        },
        "repeated_line_candidates": review["repeated_line_candidates"],
    }


def create_director_plan(segments: list[dict[str, Any]], language: str = "unknown") -> dict[str, Any]:
    """Return an AI review when configured, otherwise a conservative local plan."""
    if not segments:
        return {"summary": "No transcript segments were available.", "status": "empty"}
    try:
        plan = _gemini_review(segments, language)
        plan["status"] = "ai_review"
        plan["provider"] = "gemini"
        return plan
    except Exception as exc:
        fallback = _fallback_review(segments, language)
        fallback["status"] = "fallback_review"
        fallback["provider"] = "local"
        fallback["provider_note"] = str(exc)[:1200]
        return fallback
