"""Resolve user-supplied licensed B-roll clips into safe timeline overlays."""
from __future__ import annotations

from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}


def resolve_broll_assets(
    shots: list[dict[str, Any]], asset_dir: Path | None
) -> list[dict[str, Any]]:
    """Match shot_N.ext files to shot segment indexes; never fetch remote assets."""
    if asset_dir is None or not asset_dir.exists():
        return []
    if not asset_dir.is_dir():
        raise ValueError("B-roll asset path must be a directory.")
    resolved = []
    for shot in shots:
        index = shot.get("segment_index")
        if not isinstance(index, int) or isinstance(index, bool):
            continue
        matches = sorted(
            p for p in asset_dir.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
            and p.stem.casefold() == f"shot_{index}".casefold()
        )
        if not matches:
            continue
        resolved.append({
            **shot,
            "asset_path": str(matches[0].resolve()),
            "asset_status": "matched_user_supplied_asset",
        })
    return resolved


def build_broll_filter(
    base_label: str, assets: list[dict[str, Any]], first_input_index: int
) -> tuple[str, str]:
    """Return filter graph and final video label for full-frame B-roll replacement."""
    current = base_label
    filters = []
    for offset, asset in enumerate(assets):
        input_index = first_input_index + offset
        start = float(asset["edited_start_seconds"])
        end = float(asset["edited_end_seconds"])
        if end <= start:
            continue
        scaled = f"broll_scaled_{offset}"
        output = f"broll_mix_{offset}"
        filters.append(
            f"[{input_index}:v]setpts=PTS-STARTPTS,fps=30,scale=1080:1920:"
            f"force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
            f"format=yuv420p[{scaled}]"
        )
        filters.append(
            f"[{current}][{scaled}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})':"
            f"eof_action=pass:shortest=0:format=auto[{output}]"
        )
        current = output
    return ";".join(filters), current
