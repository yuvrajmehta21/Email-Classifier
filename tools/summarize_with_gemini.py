#!/usr/bin/env python3
"""
summarize_with_gemini.py — Gemini 2.5 Flash summarizer for the daily inbox digest.

Input: normalized email dict (output of normalize_email.normalize), but using
the full body — the daily-summary fetcher selects `body` instead of just
`bodyPreview`, so the caller passes the full body in the `body` field.

Output: list of exactly three short bullet strings, each one line, ranked by
urgency (deadlines, money, escalations, requests for action).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = """You are summarizing a single email for a garment-manufacturing business owner who is scanning his daily digest. He wants to immediately see the most urgent, actionable parts.

You MUST return ONLY valid JSON. No markdown, no commentary.

OUTPUT SCHEMA:
{"bullets": ["...", "...", "..."]}

RULES:
- Return EXACTLY 3 bullets.
- Each bullet is ONE line, maximum ~120 characters. No line breaks inside a bullet.
- Rank bullets by urgency: deadlines, money figures, escalations, explicit asks first; context/background later.
- Be specific. Include numbers, names, dates, deadlines if present. Do not say "the email discusses X" — state X directly.
- No salutations, signatures, or pleasantries.
- If the email is genuinely empty or has no usable content, return three bullets describing that fact.
- Do not invent facts not present in the email."""


def _user_message(item: dict) -> str:
    return (
        f"Sender: {item.get('sender_address','')}\n"
        f"Subject: {item.get('subject','')}\n\n"
        f"Body:\n{item.get('body','')}"
    )


def summarize(item: dict) -> list[str]:
    if not GEMINI_API_KEY:
        sys.exit("GEMINI_API_KEY not set in .env")

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": _user_message(item)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]

    try:
        decision = json.loads(text)
        bullets = decision.get("bullets", [])
        if not isinstance(bullets, list) or not bullets:
            raise ValueError("no bullets")
        return [str(b).strip() for b in bullets[:3]]
    except (json.JSONDecodeError, ValueError):
        return ["[summary unavailable]"]


def main():
    raw = json.load(sys.stdin)
    items = raw if isinstance(raw, list) else [raw]
    out = [{"message_id": i.get("message_id"), "bullets": summarize(i)} for i in items]
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
