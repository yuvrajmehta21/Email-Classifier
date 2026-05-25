#!/usr/bin/env python3
"""
outlook_move_message.py — Move a single Outlook message to a destination folder.

Replaces the n8n "Move to folder" node. Returns the new message resource
(Graph returns a new id after a move because the message is copied across
folders internally).

Usage:
    python tools/outlook_move_message.py --message-id <id> --folder-id <id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.outlook_auth import get_access_token  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"


def move_message(message_id: str, folder_id: str) -> dict:
    token = get_access_token()
    url = f"{GRAPH}/me/messages/{message_id}/move"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"destinationId": folder_id},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message-id", required=True)
    ap.add_argument("--folder-id", required=True)
    args = ap.parse_args()
    result = move_message(args.message_id, args.folder_id)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
