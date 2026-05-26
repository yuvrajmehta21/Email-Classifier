#!/usr/bin/env python3
"""
categorize_by_employee.py — Decide which employee section(s) an email belongs
to in the daily digest.

Routing algorithm:
  1) If the first non-empty line of the body starts with "Hi/Hello/Dear <name>"
     and <name> matches a listed employee, route to that employee only.
  2) Else, route to every employee whose name appears (case-insensitive
     substring) in the sender display name or any To display name.
     CC is intentionally excluded — being CC'd on a long thread shouldn't
     pull a person into the digest under every email on that thread.
  3) Else, return [] — caller files the email under "Other reads".

Known limitation: short first names ("Amit", "Indra") can substring-match
longer names ("Amitabh", "Indrajit"). Acceptable trade-off for v1; if false
positives surface, add a per-employee email-address allowlist later.

Input: the raw Graph message dict (NOT the normalized form — we need the
display names that normalize_email drops). The body is read from
msg["body"]["content"] (plain text per the fetch tool's Prefer header).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.employees import EMPLOYEES, GREETING_PREFIXES  # noqa: E402


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _employee_in_text(text: str) -> str | None:
    low = text.lower()
    for emp in EMPLOYEES:
        if emp.lower() in low:
            return emp
    return None


def _greeting_target(body: str) -> str | None:
    first = _first_nonempty_line(body)
    if not first:
        return None
    low = first.lower()
    for prefix in GREETING_PREFIXES:
        if low.startswith(prefix + " ") or low.startswith(prefix + ","):
            # Look at the rest of the line after the greeting word
            rest = first[len(prefix):].lstrip(" ,")
            return _employee_in_text(rest)
    return None


def _display_names(msg: dict) -> list[str]:
    names: list[str] = []
    sender = (msg.get("from") or {}).get("emailAddress") or {}
    if sender.get("name"):
        names.append(sender["name"])
    for r in msg.get("toRecipients") or []:
        ea = r.get("emailAddress") or {}
        if ea.get("name"):
            names.append(ea["name"])
    return names


def categorize(msg: dict) -> list[str]:
    body = ((msg.get("body") or {}).get("content")) or msg.get("bodyPreview") or ""

    pinned = _greeting_target(body)
    if pinned:
        return [pinned]

    names_blob = " ".join(_display_names(msg))
    low = names_blob.lower()
    matches = [emp for emp in EMPLOYEES if emp.lower() in low]
    return matches
