#!/usr/bin/env python3
"""
apply_label.py — Confidence gate + label-to-folderId mapping. Port of the n8n
"mapping" code node.

Rules (all from the n8n version):
- confidence <= 0.6  -> final_label = "Needs review"
- bucket_label not in ALLOWED_LABELS -> final_label = "Needs review"
- folder_id is looked up from LABEL_TO_FOLDER_ID
- If JSON parsing failed upstream (no bucket_label), fall back to "Needs review"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.folder_ids import (  # noqa: E402
    ALLOWED_LABELS,
    LABEL_TO_FOLDER_ID,
    NEEDS_REVIEW_FOLDER_ID,
)


def apply_label(item: dict) -> dict:
    bucket = item.get("bucket_label")
    try:
        confidence = float(item.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    final_label = bucket if bucket in ALLOWED_LABELS else "Needs review"
    if confidence <= 0.6:
        final_label = "Needs review"

    folder_id = LABEL_TO_FOLDER_ID.get(final_label, NEEDS_REVIEW_FOLDER_ID)

    return {
        **item,
        "final_label": final_label,
        "confidence": confidence,
        "folder_id": folder_id,
    }


def main():
    raw = json.load(sys.stdin)
    items = raw if isinstance(raw, list) else [raw]
    out = [apply_label(i) for i in items]
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
