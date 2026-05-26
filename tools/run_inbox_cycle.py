#!/usr/bin/env python3
"""
run_inbox_cycle.py — Single-command orchestrator for one polling cycle.

Pipeline: fetch_unread -> normalize -> pre_classify -> classify_with_gemini ->
apply_label -> move_message. Idempotency guard via .tmp/seen_message_ids.json.

The cloud routine should invoke just this script. Each step is also runnable
standalone for debugging.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.apply_label import apply_label  # noqa: E402
from tools.classify_with_gemini import classify  # noqa: E402
from tools.normalize_email import normalize  # noqa: E402
from tools.outlook_fetch_unread import fetch_unread  # noqa: E402
from tools.outlook_move_message import move_message  # noqa: E402
from tools.pre_classify import pre_classify  # noqa: E402

SEEN_PATH = ROOT / ".tmp" / "seen_message_ids.json"
SEEN_LIMIT = 5000  # cap so the file never grows unbounded

# Emails whose subject starts with this prefix are left untouched in the
# Inbox — they are the daily-summary digests sent by run_daily_summary.py,
# and the client wants them to remain visible in the Inbox until he reads
# them. Once read, they no longer match `isRead eq false` and the classifier
# won't see them again anyway.
SKIP_SUBJECT_PREFIX = "Daily Inbox Summary"


def _load_seen() -> list[str]:
    if not SEEN_PATH.exists():
        return []
    try:
        return json.loads(SEEN_PATH.read_text())
    except json.JSONDecodeError:
        return []


def _save_seen(ids: list[str]) -> None:
    SEEN_PATH.parent.mkdir(exist_ok=True)
    SEEN_PATH.write_text(json.dumps(ids[-SEEN_LIMIT:]))


def run_cycle(limit: int, dry_run: bool) -> dict:
    seen = set(_load_seen())
    started = datetime.now(timezone.utc).isoformat()

    raw_messages = fetch_unread(limit)
    new_messages = [m for m in raw_messages if m.get("id") not in seen]
    skipped = [m for m in new_messages if (m.get("subject") or "").startswith(SKIP_SUBJECT_PREFIX)]
    new_messages = [m for m in new_messages if not (m.get("subject") or "").startswith(SKIP_SUBJECT_PREFIX)]

    results = []
    for msg in new_messages:
        try:
            norm = normalize(msg)
            pre = pre_classify(norm)
            ai = classify(pre)
            decided = apply_label(ai)

            move_target = decided["folder_id"]
            if not dry_run:
                move_message(decided["message_id"], move_target)
                seen.add(decided["message_id"])

            results.append({
                "message_id": decided["message_id"],
                "subject": decided.get("subject", ""),
                "sender": decided.get("sender_address", ""),
                "sender_type": decided.get("sender_type"),
                "addressed_to_me": decided.get("addressed_to_me"),
                "model_label": ai.get("bucket_label"),
                "final_label": decided["final_label"],
                "confidence": decided["confidence"],
                "moved": not dry_run,
            })
        except Exception as e:
            results.append({
                "message_id": msg.get("id"),
                "error": str(e),
                "trace": traceback.format_exc(),
            })

    if not dry_run:
        _save_seen(sorted(seen))

    return {
        "started_at": started,
        "fetched": len(raw_messages),
        "new": len(new_messages),
        "skipped": len(skipped),
        "processed": len([r for r in results if "error" not in r]),
        "errors": len([r for r in results if "error" in r]),
        "results": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25, help="Max unread messages per cycle.")
    ap.add_argument("--dry-run", action="store_true", help="Classify but do not move.")
    args = ap.parse_args()

    summary = run_cycle(args.limit, args.dry_run)
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    sys.exit(0 if summary["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
