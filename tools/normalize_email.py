#!/usr/bin/env python3
"""
normalize_email.py — Flatten a Graph message into the fields the rest of the
pipeline uses. Direct port of the n8n "Normalize" Set node.

Library use:
    from tools.normalize_email import normalize
    norm = normalize(graph_message_dict)

CLI use (for piping):
    python tools/outlook_fetch_unread.py | python tools/normalize_email.py
"""

from __future__ import annotations

import json
import sys


def normalize(msg: dict) -> dict:
    sender_address = (msg.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""
    domain = ""
    if "@" in sender_address:
        domain = sender_address.split("@", 1)[1].lower()

    return {
        "sender_address": sender_address,
        "sender_domain": domain,
        "subject": msg.get("subject", "") or "",
        "body": msg.get("bodyPreview", "") or "",
        "thread_id": msg.get("conversationId", "") or "",
        "message_id": msg.get("id", "") or "",
        "to": msg.get("toRecipients", []) or [],
        "cc": msg.get("ccRecipients", []) or [],
    }


def main():
    raw = json.load(sys.stdin)
    items = raw if isinstance(raw, list) else [raw]
    out = [normalize(m) for m in items]
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
