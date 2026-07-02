# Classify Inbox — One Polling Cycle

## Objective
Pull unread messages from Vikram's watched Outlook folder, classify each into one of seven buckets, and move it to the matching folder. This is what the VPS's cron job fires every minute.

## Required inputs (from `.env`)
- `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_REFRESH_TOKEN` — Microsoft Graph auth (see `outlook_setup.md` for how these get there)
- `MS_CLIENT_SECRET` — only if the Azure app was registered as confidential
- `GEMINI_API_KEY` — for the classifier

## Tool sequence

The orchestrator script does all of this in one process:

```
python tools/run_inbox_cycle.py
```

Add `--dry-run` to classify without moving. Add `--limit N` to cap messages per cycle (default 25).

Under the hood, per message:
1. `tools/outlook_fetch_unread.py` — `GET /me/mailFolders/{SOURCE_FOLDER_ID}/messages?$filter=isRead eq false`
2. `tools/normalize_email.py` — flatten Graph fields
3. `tools/pre_classify.py` — deterministic rules (domain lists, addressed_to_me)
4. `tools/classify_with_gemini.py` — Gemini 2.5 Flash, JSON output
5. `tools/apply_label.py` — confidence gate (`<= 0.6` → "Needs review"), label → folder_id lookup
6. `tools/outlook_move_message.py` — `POST /me/messages/{id}/move`

Idempotency: processed message IDs are appended to `.tmp/seen_message_ids.json` (capped at 5000). A message that somehow re-appears unread isn't reprocessed.

## Expected output
JSON summary on stdout:
```json
{
  "started_at": "...",
  "fetched": 12,
  "new": 12,
  "processed": 12,
  "errors": 0,
  "results": [ { "message_id": "...", "final_label": "Urgent", "confidence": 0.85, "moved": true }, ... ]
}
```
Exit code is 0 on full success, 1 if any message errored.

## Carve-out: daily-summary digests stay in Inbox

Emails whose subject starts with `Daily Inbox Summary` are sent by the companion daily-summary tool (see [daily_summary.md](daily_summary.md)) and the client wants them to remain visible in the Inbox until he reads them. The orchestrator filters these out after `fetch_unread` and before classification — they are neither classified nor moved. The `skipped` count in the JSON output reflects how many were filtered out this cycle. Once Vikram reads the digest it stops matching `isRead eq false` and is no longer fetched.

## Edge cases & known behavior

- **Any per-message failure (Gemini timeout, Graph hiccup, unexpected exception)** — the email is moved to "Needs review" and marked seen instead of being left unread. Left unread it would be refetched and retried every minute forever: on 2026-06-22/23 one email looped 363 timed-out Gemini calls over ~12 hours (~$45 — Google bills timed-out requests). If even the fallback move fails, the email retries next cycle, but only up to `MAX_ATTEMPTS = 5` cycles (tracked in `.tmp/attempt_counts.json`); after that it is abandoned — marked seen and left visible in the inbox for manual handling. Worst case per poison email is therefore 5 Gemini calls, ever.
- **Input caps** — `classify_with_gemini.py` sends at most `MAX_RECIPIENTS = 20` To/Cc addresses (with a `(+N more)` marker) and `MAX_BODY_CHARS = 2000` of body, so no single email can blow up the request payload.
- **Thinking disabled** — the classifier calls Gemini with `thinkingBudget: 0`; a temperature-0 JSON label needs no reasoning tokens, and thinking bills at the higher output rate.
- **Gemini returns invalid JSON** — `classify_with_gemini.py` falls back to `bucket_label="Needs review", confidence=0`. The confidence gate then routes to "Needs review" deterministically.
- **Confidence ≤ 0.6** — overrides whatever label Gemini chose. Forced to "Needs review".
- **Internal sender writing to a BBG/Roxy address** — `pre_classify.py` reclassifies these to `BBG_Roxy` regardless of body content (see the recipient-domain check).
- **Promotional / Miscellaneous / BBG_Roxy hard overrides** — domains in `config/domain_lists.py` bypass the AI; the system prompt forces `confidence=1.0` for these.
- **`addressed_to_me`** — the precomputed flag only fires for `Buyer` or `Internal` senders, and requires both `vikram@conceptclothing.co.in` in `To` *and* one of `["vikram", "vikram mehta", "sir"]` in the first non-empty body line.
- **Travel / personal trip** (content-based, no domain list) — for travel/hotel/airline/booking emails the prompt splits two cases: *promotional* travel (offers, discounts, loyalty marketing, "book now") → **Promotions**; a *genuine booked trip* (reservation/itinerary/confirmation, or a hotel GM/concierge coordinating his stay) → **Addressed to me** if personally addressed to Vikram (greeting names him, or his email is in `To`), otherwise **Miscellaneous** (e.g. automated "Dear Guest"). This is the one path where an `Unknown`-sender email can land in "Addressed to me" without the `addressed_to_me` flag. Ambiguous promo-vs-real cases fall through to Needs review via the `≤ 0.6` gate. Recipients (`To`/`Cc`) are now passed to the model so it can see whether Vikram is a direct recipient.
- **Refresh token rotation** — Microsoft sometimes returns a new refresh token. `outlook_auth.py` writes it back to `.env`. In the cloud routine, the routine's environment is the source of truth; rotation handling there is to update the routine's secret if a token error appears in logs.

## Updating the domain lists
The buyer / internal / BBG-Roxy / always-promo / always-misc lists live in `config/domain_lists.py`. Edit and commit. No runtime reload — the next routine cycle picks up the change.

## Updating the prompt
The classifier prompt is in `tools/classify_with_gemini.py` (`SYSTEM_PROMPT`). Keep the confidence-rules block in sync with `apply_label.py`'s confidence gate (currently `<= 0.6` → Needs review).

## Scheduling
Runs as a `cron` job on a small DigitalOcean droplet (see [NEXT_STEPS.md](../NEXT_STEPS.md) for setup):
- Cron: `* * * * *` (every minute, matches the original n8n trigger)
- Wrapped in `flock` to prevent overlapping runs if any single cycle exceeds 60s
- Logs to `~/inbox-cycle.log` on the droplet
- Secrets live in the droplet's `.env`, copied over via scp; private key file lives at `.secrets/concept-classifier.key`

## Verification (run locally before scheduling)
```bash
# 1. Auth works:
python tools/outlook_auth.py --print-token | head -c 40

# 2. Fetch a few unread messages:
python tools/outlook_fetch_unread.py --limit 3

# 3. Full pipeline, no moves:
python tools/run_inbox_cycle.py --dry-run --limit 3

# 4. Real run on a single test email you sent yourself:
python tools/run_inbox_cycle.py --limit 1
```
