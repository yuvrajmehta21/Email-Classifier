#!/usr/bin/env python3
"""
run_daily_summary.py — Daily 8 AM IST inbox digest for Vikram.

Pipeline: fetch_read -> normalize -> categorize_by_employee -> summarize_with_gemini
-> build HTML grouped by employee -> outlook_send_mail (to Vikram, from Vikram).

No idempotency state. Every run reads whatever is currently read-and-in-Inbox,
because Vikram's working pattern is to move emails he wants to revisit back
into the Inbox. Yesterday's digest may overlap with today's — that's by design.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.employees import EMPLOYEES  # noqa: E402
from tools.categorize_by_employee import categorize  # noqa: E402
from tools.normalize_email import normalize  # noqa: E402
from tools.outlook_fetch_read import fetch_read  # noqa: E402
from tools.outlook_send_mail import send  # noqa: E402
from tools.summarize_with_gemini import summarize  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
OTHER_BUCKET = "Other reads"


def _sender_display(msg: dict) -> str:
    sender = (msg.get("from") or {}).get("emailAddress") or {}
    name = sender.get("name") or ""
    addr = sender.get("address") or ""
    if name and addr:
        return f"{name} <{addr}>"
    return name or addr or "(unknown sender)"


def _process_one(msg: dict) -> dict:
    norm = normalize(msg)
    # Replace truncated bodyPreview with the full plain-text body the
    # daily fetcher selected. Falls back to bodyPreview if absent.
    full_body = ((msg.get("body") or {}).get("content")) or norm.get("body", "")
    norm["body"] = full_body

    buckets = categorize(msg)
    bullets = summarize(norm)

    return {
        "message_id": norm["message_id"],
        "subject": norm.get("subject", ""),
        "sender_display": _sender_display(msg),
        "buckets": buckets or [],
        "bullets": bullets,
    }


def _group(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {emp: [] for emp in EMPLOYEES}
    groups[OTHER_BUCKET] = []
    for it in items:
        if it["buckets"]:
            for emp in it["buckets"]:
                if emp in groups:
                    groups[emp].append(it)
        else:
            groups[OTHER_BUCKET].append(it)
    return groups


def _render_html(groups: dict[str, list[dict]], date_str: str, total: int) -> str:
    e = html.escape
    parts: list[str] = []
    parts.append(
        f"<h2>Daily Inbox Summary &mdash; {e(date_str)}</h2>"
        f"<p>{total} read email(s) in your Inbox.</p>"
    )

    section_order = EMPLOYEES + [OTHER_BUCKET]
    for section in section_order:
        items = groups.get(section, [])
        if not items:
            continue
        parts.append(f"<h3>{e(section)}</h3>")
        for it in items:
            parts.append(
                f'<p style="margin-bottom:4px;"><b>{e(it["subject"] or "(no subject)")}</b>'
                f' &mdash; from {e(it["sender_display"])}</p>'
            )
            parts.append("<ul>")
            for b in it["bullets"]:
                parts.append(f"<li>{e(b)}</li>")
            parts.append("</ul>")

    if total > 0 and not any(groups[s] for s in section_order):
        parts.append("<p><i>No emails matched any section.</i></p>")
    if total == 0:
        parts.append("<p><i>No read emails in the Inbox right now.</i></p>")

    return "\n".join(parts)


def run(limit: int, dry_run: bool) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now(IST).strftime("%Y-%m-%d")

    messages = fetch_read(limit)

    results: list[dict] = []
    errors: list[dict] = []
    for msg in messages:
        try:
            results.append(_process_one(msg))
        except Exception as ex:
            errors.append({
                "message_id": msg.get("id"),
                "error": str(ex),
                "trace": traceback.format_exc(),
            })

    groups = _group(results)
    html_body = _render_html(groups, date_str, len(results))
    subject = f"Daily Inbox Summary — {date_str}"

    sent = False
    if not dry_run and results:
        send(subject, html_body)
        sent = True

    return {
        "started_at": started,
        "date_ist": date_str,
        "fetched": len(messages),
        "processed": len(results),
        "errors_count": len(errors),
        "sent": sent,
        "subject": subject,
        "html_body": html_body if dry_run else None,
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="Max read messages to summarize.")
    ap.add_argument("--dry-run", action="store_true", help="Build the summary but do not send.")
    args = ap.parse_args()

    summary = run(args.limit, args.dry_run)
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    sys.exit(0 if summary["errors_count"] == 0 else 1)


if __name__ == "__main__":
    main()
