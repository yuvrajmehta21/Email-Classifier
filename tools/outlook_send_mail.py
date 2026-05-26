#!/usr/bin/env python3
"""
outlook_send_mail.py — Send an email as Vikram via Graph /me/sendMail.

Sender is implicit (the authenticated user — Vikram), so when this is used to
send the daily summary to VIKRAM_EMAIL, Vikram receives the email from himself.

Requires the Mail.Send scope on the refresh token. If you see a 403 here, the
refresh token was bootstrapped before Mail.Send was added to outlook_auth.SCOPES.
Re-run `python tools/outlook_auth.py --bootstrap` once locally to fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.domain_lists import VIKRAM_EMAIL  # noqa: E402
from tools.outlook_auth import get_access_token  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"


def send(subject: str, html: str, to: str = VIKRAM_EMAIL) -> None:
    token = get_access_token()
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    r = requests.post(
        f"{GRAPH}/me/sendMail",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    # Graph returns 202 Accepted with empty body on success.
    r.raise_for_status()
