#!/usr/bin/env python3
"""
outlook_fetch_unread.py — Fetch unread messages from Vikram's watched folder.

Replaces the n8n "Microsoft Outlook Trigger" node. Outputs a JSON array of
raw Graph message resources to stdout — exactly what the rest of the pipeline
expects to receive.

Usage:
    python tools/outlook_fetch_unread.py [--limit 25]
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


def fetch_unread(limit: int = 25) -> list[dict]:
    token = get_access_token()
    url = f"{GRAPH}/me/mailFolders/{SOURCE_FOLDER_ID}/messages"
    params = {
        "$filter": "isRead eq false",
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$select": "id,conversationId,subject,bodyPreview,from,toRecipients,ccRecipients,receivedDateTime,isRead",
    }
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("value", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()
    messages = fetch_unread(args.limit)
    json.dump(messages, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
