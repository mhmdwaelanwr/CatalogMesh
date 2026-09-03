from __future__ import annotations

from pathlib import Path
from typing import Any

from .review_center import load_manifest, review_summary


def open_review_queue(path_or_dir: str | Path, *, limit: int = 50) -> dict[str, Any]:
    """Return a read-only summary of groups that still need human review."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    manifest, path = load_manifest(Path(path_or_dir))
    pending: list[dict[str, Any]] = []
    for group in manifest.get("groups", []):
        if bool(group.get("approved")):
            continue
        photos = list(group.get("photos", []))
        pending.append(
            {
                "group_id": str(group.get("group_id", "")),
                "category": str(group.get("category", "")),
                "brand": str(group.get("brand", "")),
                "model": str(group.get("model", "")),
                "notes": str(group.get("notes", "")),
                "photo_count": len(photos),
                "needs_review_photos": [
                    {
                        "filename": str(photo.get("filename", "")),
                        "view": str(photo.get("view", "")),
                        "confidence": photo.get("confidence", 0.0),
                        "reason": str(photo.get("reason", "")),
                        "relative_path": str(photo.get("relative_path", "")),
                    }
                    for photo in photos
                    if str(photo.get("original_status", "")).lower() == "needs_review"
                ],
            }
        )
        if len(pending) >= limit:
            break
    return {
        "manifest": str(path),
        "summary": review_summary(manifest),
        "pending_groups": pending,
        "returned_groups": len(pending),
        "read_only": True,
        "human_review_required": bool(pending),
    }
