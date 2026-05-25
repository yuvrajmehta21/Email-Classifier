#!/usr/bin/env python3
"""
pre_classify.py — Deterministic pre-classification. Port of the n8n "AI_input"
JS code node.

Adds two fields to a normalized email:
  sender_type      — Buyer | Internal | Unknown | Promotional | Miscellaneous | BBG_Roxy
  addressed_to_me  — bool

Rule precedence (highest first):
  1. ALWAYS_PROMOTIONAL    -> sender_type=Promotional
  2. ALWAYS_MISCELLANEOUS  -> sender_type=Miscellaneous
  3. BBG_ROXY_DOMAINS      -> sender_type=BBG_Roxy
  4. DOMAIN_LIST match     -> Buyer or Internal
  5. Internal sender writing TO a BBG/Roxy recipient -> reclass to BBG_Roxy
  6. addressed_to_me only fires for Buyer/Internal AND requires both
     Vikram in To AND his name in the first non-empty body line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.domain_lists import (  # noqa: E402
    ALWAYS_MISCELLANEOUS,
    ALWAYS_PROMOTIONAL,
    BBG_ROXY_DOMAINS,
    DOMAIN_LIST,
    VIKRAM_EMAIL,
    VIKRAM_NAMES,
)


def _recipient_domains(recipients: list) -> list[str]:
    out = []
    for r in recipients or []:
        addr = (r or {}).get("emailAddress", {}).get("address", "") or ""
        if "@" in addr:
            out.append(addr.split("@", 1)[1].lower().strip())
    return out


def pre_classify(norm: dict) -> dict:
    domain = (norm.get("sender_domain") or "").lower().strip()

    if domain in ALWAYS_PROMOTIONAL:
        return {**norm, "sender_type": "Promotional", "addressed_to_me": False}
    if domain in ALWAYS_MISCELLANEOUS:
        return {**norm, "sender_type": "Miscellaneous", "addressed_to_me": False}
    if domain in BBG_ROXY_DOMAINS:
        return {**norm, "sender_type": "BBG_Roxy", "addressed_to_me": False}

    match = next((r for r in DOMAIN_LIST if r["domain"] == domain), None)
    sender_type = "Unknown"
    if match:
        sender_type = "Internal" if match["type"] == "Internal" else "Buyer"

    # Internal employee writing to BBG/Roxy → reclass to BBG_Roxy.
    if sender_type == "Internal":
        recipient_domains = _recipient_domains(norm.get("to", []) + norm.get("cc", []))
        if any(d in BBG_ROXY_DOMAINS for d in recipient_domains):
            return {**norm, "sender_type": "BBG_Roxy", "addressed_to_me": False}

    addressed_to_me = False
    if sender_type in ("Buyer", "Internal"):
        to_addrs = [
            ((r or {}).get("emailAddress", {}).get("address", "") or "").lower().strip()
            for r in norm.get("to", []) or []
        ]
        in_to = VIKRAM_EMAIL.lower() in to_addrs

        first_line = ""
        for line in (norm.get("body") or "").splitlines():
            stripped = line.strip()
            if stripped:
                first_line = stripped.lower()
                break

        name_in_first_line = any(name in first_line for name in VIKRAM_NAMES)
        addressed_to_me = in_to and name_in_first_line

    return {**norm, "sender_type": sender_type, "addressed_to_me": addressed_to_me}


def main():
    raw = json.load(sys.stdin)
    items = raw if isinstance(raw, list) else [raw]
    out = [pre_classify(n) for n in items]
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
