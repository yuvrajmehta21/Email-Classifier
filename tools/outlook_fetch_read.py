#!/usr/bin/env python3
"""
outlook_fetch_read.py — Fetch READ messages from Vikram's watched Inbox folder.

This is the source for the daily summary. Vikram moves emails he wants to
revisit back into the Inbox, so by 8 AM the Inbox holds his curated set of
already-read items to act on.

Differences vs outlook_fetch_unread.py:
- $filter=isRead eq true
- $select includes full body (not just bodyPreview)
- Prefer header asks Graph for plain-text body so we don't have to strip HTML

Usage:
    python tools/outlook_fetch_read.py [--limit 100]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.folder_ids import SOURCE_FOLDER_ID  # noqa: E402
from tools.outlook_auth import get_access_token  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"


def fetch_read(limit: int = 100) -> list[dict]:
    token = get_access_token()
    url = f"{GRAPH}/me/mailFolders/{SOURCE_FOLDER_ID}/messages"
    params = {
        "$filter": "isRead eq true",
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$select": "id,conversationId,subject,bodyPreview,body,from,toRecipients,ccRecipients,receivedDateTime,isRead",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": 'outlook.body-content-type="text"',
    }
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("value", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    messages = fetch_read(args.limit)
    json.dump(messages, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
