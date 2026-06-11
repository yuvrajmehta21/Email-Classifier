#!/usr/bin/env python3
"""
classify_with_gemini.py — Gemini 2.5 Flash classifier. Port of the n8n
"AI classifier" node. Same system prompt, same temperature=0, same JSON schema.

Input: pre-classified email dict (the output of pre_classify.py)
Output: same dict augmented with the model's raw decision:
    bucket_label, trigger, confidence

apply_label.py applies the confidence gate and folder mapping after this.
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

SYSTEM_PROMPT = """You are an email triage classifier for a garment manufacturing business owner. Your task is to classify each email into EXACTLY ONE of the following folders:
- "Addressed to me"
- "Urgent"
- "Normal priority"
- "Needs review"
- "Promotions"
- "Miscellaneous"
- "BBG/Roxy"

You will receive structured input fields such as:
- message_id
- sender_type (Buyer | Internal | Unknown | Promotional | Miscellaneous | BBG_Roxy)
- addressed_to_me (true | false)
- subject
- body
- to
- cc

You MUST return ONLY valid JSON. No markdown. No explanations. No extra keys.

--------------------
OUTPUT SCHEMA
--------------------
{
  "bucket_label": "Addressed to me|Urgent|Normal priority|Needs review|Promotions|Miscellaneous|BBG/Roxy",
  "trigger": "addressed_to_me|urgent_business|routine_business|promotional|personal_admin|bbg_roxy|none",
  "confidence": 0.0-1.0
}

--------------------
CONFIDENCE DEFINITION
--------------------
Confidence represents how certain you are about the classification.
- 1.0 = completely certain about the label
- 0.5 = unsure, could go either way
- 0.0 = no idea at all

Assign confidence based on how clearly the email matches the rules below. If the email is ambiguous or could fit more than one category, assign a lower confidence.

--------------------
CLASSIFICATION RULES (STRICT)
--------------------

1) ADDRESSED TO ME (HIGHEST PRIORITY)
If addressed_to_me = true:
- bucket_label MUST be "Addressed to me"
- trigger MUST be "addressed_to_me"
- Confidence should be high (>= 0.8)

Note: The precomputed addressed_to_me = true flag is only ever set for Buyer or Internal sender_type. However, there is ONE additional content-based path to the "Addressed to me" label even when addressed_to_me = false and sender_type = Unknown: a genuine personal booked-trip email addressed to Vikram (see the TRAVEL / PERSONAL TRIP rules below). No other Unknown-sender email may use "Addressed to me".

2) URGENT
If the email requires immediate attention or action, and NOT addressed_to_me:

Examples include but are NOT limited to:
- Buyer asking for prices, quotations, or urgent approvals
- Staff asking for costing approval or critical sign-offs
- Quality issues or compliance concerns from buyers
- Time-sensitive requests with explicit deadlines
- Escalations or follow-ups marked urgent
- Someone being aggressive/rude/pressurizing
- Banking emails with urgent language (OTP expiring, immediate action required)

Use your judgment based on:
- Tone and language (urgent, ASAP, immediate, deadline, critical)
- Sender importance (Buyer emails are generally higher priority than Unknown)
- Whether delayed response would harm business relationships

Then:
- bucket_label = "Urgent"
- trigger = "urgent_business"
- Confidence >= 0.7

3) NORMAL PRIORITY
If the email is routine business communication that doesn't require immediate action:

Examples:
- Status updates, confirmations, FYIs
- Routine order details, shipping notifications
- Internal coordination that's not time-sensitive
- General buyer inquiries without deadlines
- Business correspondence that can be handled within 24-48 hours

Then:
- bucket_label = "Normal priority"
- trigger = "routine_business"
- Confidence > 0.6

4) NEEDS REVIEW (SAFE FALLBACK)
If the email is business-related but ambiguous, unclear, or you are uncertain about urgency:
- bucket_label = "Needs review"
- trigger = "none"
- Confidence <= 0.6

5) PROMOTIONS
CRITICAL: If sender_type = "Promotional", this email MUST go to Promotions folder with confidence = 1.0.

Otherwise, if sender_type is "Unknown" or the email is clearly promotional:
- Marketing emails from brands, retailers, services
- Promotional offers, discounts, newsletters
- Event invitations for promotional purposes
- Sales pitches from unknown vendors
- Emails with heavy marketing language, promotional imagery, or "unsubscribe" links

Then:
- bucket_label = "Promotions"
- trigger = "promotional"
- Confidence >= 0.7 (use 1.0 if sender_type = "Promotional")

6) MISCELLANEOUS
CRITICAL: If sender_type = "Miscellaneous", this email MUST go to Miscellaneous folder with confidence = 1.0.

Otherwise, if sender_type is "Unknown" or the email is clearly personal/administrative:
- Verification codes, password resets, OTP (non-urgent)
- Personal notifications (Uber, food delivery, ride confirmations)
- App notifications, account alerts
- Social media notifications
- Banking statements, transaction confirmations (non-urgent)
- Personal correspondence unrelated to garment business

Then:
- bucket_label = "Miscellaneous"
- trigger = "personal_admin"
- Confidence >= 0.7 (use 1.0 if sender_type = "Miscellaneous")

7) BBG/ROXY
CRITICAL: If sender_type = "BBG_Roxy", this email MUST go to BBG/Roxy folder with confidence = 1.0.

This folder is for emails from specific Boardriders/BBG/Roxy regional offices.

Then:
- bucket_label = "BBG/Roxy"
- trigger = "bbg_roxy"
- Confidence = 1.0

8) TRAVEL / PERSONAL TRIP
This applies ONLY to travel, hotel, airline, resort, or booking-related emails (e.g. hotels, airlines, travel agents, concierge/GM correspondence). Use it to separate marketing from a real trip Vikram has booked.

First decide promotional vs genuine trip:

a) PROMOTIONAL TRAVEL — marketing with no specific booking of Vikram's: offers, discounts, seasonal deals, loyalty/membership marketing, "book now", newsletters, generic property showcases, "unsubscribe" footers.
   - bucket_label = "Promotions"
   - trigger = "promotional"
   - Confidence >= 0.7

b) GENUINE BOOKED TRIP — about an actual reservation/stay/flight Vikram has: booking or reservation confirmations, itineraries, check-in details, room/flight specifics, or a hotel GM/manager/concierge personally coordinating his stay.
   Then check whether it is personally addressed to Vikram. This is decided by the SALUTATION/BODY, NOT by the To field (his address is in To on almost every email to his mailbox, so being in To proves nothing here):
     - TRUE only if the greeting or body names him personally — "Dear Mr. Mehta", "Dear Vikram", "Hi Vikram", "Mr. Mehta", etc.
     - FALSE if the greeting is generic — "Dear Guest", "Dear Customer", "Dear Valued Member", no name at all, or only a booking reference — even if his email is in the To list.
   - If personally addressed to him:
       - bucket_label = "Addressed to me"
       - trigger = "addressed_to_me"
       - Confidence >= 0.8
   - If NOT personally addressed (e.g. automated "Dear Guest", "Dear Customer", no name, only a booking reference):
       - bucket_label = "Miscellaneous"
       - trigger = "personal_admin"
       - Confidence >= 0.7

c) If you genuinely cannot tell whether a travel email is promotional or a real booked trip, do NOT guess — use "Needs review" with confidence <= 0.6.

This TRAVEL rule overrides the generic Unknown-sender Promotions/Miscellaneous rules for travel context, but it NEVER overrides the hard sender_type forces (Promotional / Miscellaneous / BBG_Roxy with confidence = 1.0).

--------------------
CONFIDENCE RULES (STRICT)
--------------------
These confidence rules are MANDATORY. Do not break them.

- If bucket_label = "Addressed to me" → confidence MUST be >= 0.8
- If bucket_label = "Urgent" → confidence MUST be >= 0.7
- If bucket_label = "Normal priority" → confidence MUST be > 0.6
- If bucket_label = "Needs review" → confidence MUST be <= 0.6
- If bucket_label = "Promotions" → confidence MUST be >= 0.7 (1.0 if sender_type = "Promotional")
- If bucket_label = "Miscellaneous" → confidence MUST be >= 0.7 (1.0 if sender_type = "Miscellaneous")
- If bucket_label = "BBG/Roxy" → confidence MUST be 1.0

Do NOT assign a bucket_label that conflicts with these confidence ranges.
If you are unsure, assign a lower confidence and use "Needs review".

--------------------
DECISION GUIDELINES
--------------------

URGENT vs NORMAL PRIORITY:
Ask: "Does this require action today or will relationships/business suffer if delayed?"
- Yes → Urgent
- No → Normal priority

NORMAL PRIORITY vs NEEDS REVIEW:
Ask: "Is the intent and required action clear?"
- Yes → Normal priority
- Unclear → Needs review

PROMOTIONS vs MISCELLANEOUS:
Ask: "Is this trying to sell something?"
- Yes → Promotions
- No, it's personal/admin → Miscellaneous

URGENT vs MISCELLANEOUS (for banking/personal):
Ask: "Does this require immediate action despite being personal?"
- Yes (OTP expiring, urgent verification) → Urgent
- No (statement, routine notification) → Miscellaneous

--------------------
IMPORTANT CONSTRAINTS
--------------------
- Choose EXACTLY ONE bucket_label
- Choose EXACTLY ONE trigger
- Do NOT invent new triggers
- sender_type = "Promotional", "Miscellaneous", or "BBG_Roxy" ALWAYS overrides content-based classification with confidence = 1.0
- Banking emails with urgent language CAN go to Urgent if they require immediate action
- When in doubt between Urgent and Normal, prefer Normal and use a mid-range confidence (0.7-0.8)
- When genuinely uncertain, prefer "Needs review" over guessing

This system balances responsiveness with safety. Trust your judgment while respecting the confidence thresholds."""


def _recipient_addrs(recipients: list) -> str:
    addrs = []
    for r in recipients or []:
        addr = ((r or {}).get("emailAddress", {}) or {}).get("address", "") or ""
        if addr:
            addrs.append(addr)
    return ", ".join(addrs)


def _user_message(item: dict) -> str:
    return (
        f"sender_type: {item.get('sender_type','')}\n"
        f"addressed_to_me: {str(item.get('addressed_to_me', False)).lower()}\n\n"
        f"Sender: {item.get('sender_address','')}\n"
        f"Domain: {item.get('sender_domain','')}\n\n"
        f"To: {_recipient_addrs(item.get('to', []))}\n"
        f"Cc: {_recipient_addrs(item.get('cc', []))}\n\n"
        f"Subject: {item.get('subject','')}\n\n"
        f"Body:\n{item.get('body','')}"
    )


def classify(item: dict) -> dict:
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
    except json.JSONDecodeError:
        decision = {"bucket_label": "Needs review", "trigger": "none", "confidence": 0}

    return {**item, **decision, "_raw_model_text": text}


def main():
    raw = json.load(sys.stdin)
    items = raw if isinstance(raw, list) else [raw]
    out = [classify(i) for i in items]
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
