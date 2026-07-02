# Email Classifier — Handoff

_Last updated: 2026-07-02_

This is the one document to read to pick this project up cold. It tracks **state**,
not code internals. For the working SOPs see [workflows/](workflows/); for project
rules see [CLAUDE.md](CLAUDE.md) and the parent [../CLAUDE.md](../CLAUDE.md).

---

## 1. What this project is

Two scheduled jobs run against **Vikram Mehta's Outlook mailbox** (Concept Clothing
Pvt Ltd, a garment manufacturer). Vikram is the client; the single most-valued
outcome is **a correctly-triaged inbox he can trust without babysitting**.

Priority order of goals:
1. **Per-minute classifier** (the core product) — every unread email is classified by
   Gemini 2.5 Flash into one of 7 folders and moved there. Direct replacement for a
   previously-deployed n8n workflow. Reliability here matters most.
2. **Daily digest** (secondary) — summarizes the emails Vikram has pulled *back*
   into his Inbox (his curated "deal-with-this" set) and emails him a per-employee
   summary from his own mailbox.

The whole thing runs autonomously on a $4/mo droplet. Nobody's laptop needs to be on.

---

## 2. Status at a glance

### ✅ DONE & working (verified in production)
- **Per-minute classifier** — live on the droplet, `* * * * *`. Fetches unread →
  pre-classifies by domain → Gemini → confidence gate → moves to folder.
- **Cert-based Graph auth** — confidential client, reusable refresh token. Verified
  minting tokens on both Mac and droplet.
- **Daily digest** — live on the droplet (schedule and cron lines in
  [CLAUDE.md](CLAUDE.md)). Sends from Vikram to Vikram. Verified: real sends of 47
  and 100 emails, 0 errors. (Cadence reduced from 3×/day to once daily at 10 AM IST
  on 2026-06-14 at Vikram's request.)
- **Classifier carve-out** — emails whose subject starts with `Daily Inbox Summary`
  are left in the Inbox (not classified/moved), so the digest itself stays visible.
- **Digest self-skip** — the digest filters out prior `Daily Inbox Summary` emails
  before summarizing, so it never summarizes itself.
- **Travel/trip recognition** (commit `b4a740b`) — the classifier now tells a
  promotional hotel/airline email (→ Promotions) from a genuine booked-trip email
  (→ Addressed to me if personally addressed, else Miscellaneous). Verified in
  isolation against 5 scenarios.
- **Digest timestamps** (commit `1951480`) — each email in the digest shows its
  received date/time in IST as a gray sub-line ("Thu, 11 Jun 2026, 08:07 PM IST").
  Verified via dry-run against the live mailbox.
- **Gemini short-circuit** (commit `c264642`) — `run_inbox_cycle.py` no longer calls
  Gemini for Promotional / Miscellaneous / BBG_Roxy sender_types; the prompt forced
  those to a fixed bucket at confidence 1.0 anyway, so the cycle now assigns the
  decision directly. ~20–30% fewer classifier calls, and those emails are now immune
  to Gemini outages. Log lines carry a `gemini_called` flag. Verified offline (mocked
  classify; 3 forced + 1 unknown all landed correctly) + clean post-deploy cron ticks.
- **Summarizer body truncation** (commit `0dd0c67`) — digest bodies are capped at
  4,000 chars (with a truncation marker) before the Gemini call; reply chains quote
  the whole thread below the newest message, so the tail is stale text. Verified on a
  real 8.3k-char thread: bullets equivalent to the untruncated run.
- **CLAUDE.md schedule drift fixed** (commit `dfd6710`) — docs now match the droplet
  cron. The schedule's single home is CLAUDE.md; this file deliberately doesn't
  repeat it.
- **Poison-email guards** (2026-07-02, after the $45 incident — see §10) —
  (a) any per-message failure now moves the email to "Needs review" and marks it
  seen, breaking the infinite retry loop; (b) classifier input capped at 20
  recipients / 2,000 body chars; (c) classifier runs with `thinkingBudget: 0`.
  Verified: offline tests for the fallback (live, dry-run, and move-also-fails
  paths) and caps; one live Gemini call confirming `thinkingConfig` is accepted
  with unchanged classification.

### 🔜 NOT STARTED / parked
- **Explicit Gemini prompt caching** — DROPPED by Yuvraj (2026-06-12). At this volume
  the savings are cents; Gemini 2.5's implicit prefix caching likely already helps.
  Do not build unless the bill becomes noticeable.
- **Dashboard-format digest** — attempted (Round 2) and **reverted**. An inline-HTML
  "CEO dashboard" email rendered unreadably in Outlook. Parked; if revived it should
  be a *hosted* page, not an email body. Do not re-attempt as inline email HTML.

---

## 3. Architecture & data flow

WAT framework (Workflows / Agents / Tools). Probabilistic work (Gemini) is isolated
to single steps; everything else is deterministic Python.

### Classifier (per minute)
```
outlook_fetch_unread (isRead eq false, SOURCE_FOLDER_ID)
  → [skip subjects starting "Daily Inbox Summary"]
  → normalize_email          (flatten Graph fields)
  → pre_classify             (domain lists → sender_type; addressed_to_me)
  → [short-circuit: Promotional/Miscellaneous/BBG_Roxy → forced bucket, conf 1.0,
     NO Gemini call — see DETERMINISTIC_SENDER_TYPES in run_inbox_cycle.py]
  → classify_with_gemini     (Gemini 2.5 Flash → bucket_label, confidence)
  → apply_label              (confidence ≤ 0.6 → "Needs review"; label → folder_id)
  → outlook_move_message     (POST /me/messages/{id}/move)
Idempotency: .tmp/seen_message_ids.json (capped 5000)
Orchestrator: tools/run_inbox_cycle.py
```

### Digest (daily)
```
outlook_fetch_read (isRead eq true, SOURCE_FOLDER_ID, full body)
  → [skip subjects starting "Daily Inbox Summary"]
  → normalize_email
  → categorize_by_employee   (greeting-pin, else From/To display-name match; no CC)
  → summarize_with_gemini    (3 urgency-ranked bullets; body capped at 4,000 chars)
  → render grouped HTML (per employee + "Other reads"; received time in IST per email)
  → outlook_send_mail        (POST /me/sendMail; Vikram → Vikram)
Stateless: every run re-reads the whole Inbox. No dedup file.
Orchestrator: tools/run_daily_summary.py
```

### Auth (shared)
Cert-based confidential client via `outlook_auth.py`; all Graph tools call its
`get_access_token()`. Pattern, rationale, and re-bootstrap procedure live in
[CLAUDE.md](CLAUDE.md); Azure setup in [workflows/outlook_setup.md](workflows/outlook_setup.md).
Scopes: Mail.ReadWrite, Mail.Read, Mail.Send, User.Read.

---

## 4. File-by-file: non-obvious gotchas only

What each tool does is stated in its docstring, and the pipeline shape is in §3 —
neither is repeated here. This list is only the traps you can't see from the surface:

- `tools/outlook_auth.py` — do NOT add `offline_access` to SCOPES (MSAL injects it
  itself; adding it breaks the request).
- `tools/outlook_fetch_unread.py` — selects `bodyPreview` only (~255 chars); the
  classifier never sees full bodies (see §9).
- `tools/outlook_fetch_read.py` — asks Graph for plain-text bodies via
  `Prefer: outlook.body-content-type="text"`, which is why no HTML-stripping code
  exists anywhere.
- `tools/normalize_email.py` — drops sender/recipient *display names*;
  `categorize_by_employee` reads the raw Graph message for those.
- `tools/classify_with_gemini.py` — the prompt's confidence-rules block must stay in
  sync with `apply_label.py`'s `≤ 0.6` gate AND with `DETERMINISTIC_SENDER_TYPES` in
  `run_inbox_cycle.py` (the short-circuit assumes the prompt's CRITICAL sender_type
  forces).
- `tools/summarize_with_gemini.py` — caps the body at `BODY_CHAR_LIMIT = 4000` chars
  (+ truncation marker); returns `["[summary unavailable]"]` on bad JSON rather than
  failing the digest.
- `tools/categorize_by_employee.py` — greeting-pin first, then From/To display-name
  substring. CC is *intentionally* excluded. Short names can substring-collide
  ("Amit" ⊂ "Amitabh").
- `tools/run_inbox_cycle.py` — holds the `SKIP_SUBJECT_PREFIX = "Daily Inbox Summary"`
  carve-out; removing it makes the classifier eat the digest (see §10).
- `config/employees.py` — Vikram is listed as the full name "Vikram Mehta", not
  "Vikram".
- `Inbox Automation.json` — historical n8n export, not used at runtime.

---

## 5. Setup, run & verify

All local commands run from the project root with the venv python (`.venv/bin/python`).

```bash
# Auth sanity (prints a token, no error = good):
.venv/bin/python tools/outlook_auth.py --print-token | head -c 40

# Classifier, dry-run (no moves):
.venv/bin/python tools/run_inbox_cycle.py --dry-run --limit 3

# Digest, dry-run (no send; html_body in JSON output):
.venv/bin/python tools/run_daily_summary.py --dry-run --limit 5

# Digest, real send, small cap (sends to Vikram):
.venv/bin/python tools/run_daily_summary.py --limit 1
```

Deploying a change and watching the cron logs: commands are in
[CLAUDE.md](CLAUDE.md) (Deployment / What needs me).

---

## 6. Key decisions & constraints (the "why")

- **Cert-based confidential client, NOT a client secret** — full rationale in
  [CLAUDE.md](CLAUDE.md) (Auth pattern). Short version: tenant blocks client secrets;
  the public-client alternative was tried and broke the cron. Don't revisit.
- **VPS + Linux cron, not GitHub Actions / Claude routines** — sub-hour reliable
  scheduling. GH Actions cron is best-effort and silently throttles; Claude routines
  have a 1-hour minimum. The classifier needs to fire every minute, reliably.
- **Repo is PUBLIC on GitHub** — required so the droplet can `git pull` without stored
  credentials. Safe because all secrets are gitignored and live only in `.env` /
  `.secrets/`. (Was briefly private; the droplet pull 404'd until it was made public.)
- **Digest sends from Vikram to Vikram** via `/me/sendMail` — he wanted it to "arrive
  from himself." Needed adding `Mail.Send` to scopes + one re-bootstrap (done).
- **Digest is stateless** — Vikram's workflow is to keep emails in the Inbox until
  handled, so each run re-reads everything. The same email reappearing across runs is
  by design.
- **Travel routing is content-based, no domain list** — Vikram explicitly didn't want
  to maintain a hotel-domain list. "Personally addressed" is judged by the salutation
  naming him, NOT by his address being in To (it's his mailbox — he's in To on nearly
  everything).
- **Digest dashboard email was rejected** — inline-HTML "dashboard" is unreadable in
  Outlook (it strips JS, custom fonts, editable fields). Plain grouped HTML stays.

---

## 7. Active blockers

None. Both jobs are live and healthy as of 2026-06-12.

---

## 8. Roadmap / next steps

- [x] Per-minute classifier (n8n → Python)
- [x] Cert-based auth
- [x] Daily digest (was 3×/day; reduced to once daily at 10 AM IST 2026-06-14)
- [x] Classifier carve-out + digest self-skip
- [x] Bump digest to 3×/day, then shift first slot to 10 AM IST
- [x] Travel/trip vs promotional recognition
- [x] Fix CLAUDE.md schedule drift (`dfd6710`)
- [x] Digest: received date/time per email, IST (`1951480`)
- [x] Gemini short-circuit for deterministic sender types (`c264642`)
- [x] Summarizer body truncation to 4,000 chars (`0dd0c67`)
- [~] Explicit Gemini prompt caching — DROPPED 2026-06-12; revisit only if the
  Gemini bill becomes noticeable.

Nothing is queued. Next work will come from new requests or from watching how the
short-circuit/truncation behave in production.

---

## 9. Honest limitations

- **Classifier sees only `bodyPreview` (~255 chars).** Judgments rest on the opening
  lines. Usually fine; genuinely ambiguous emails drop below the 0.6 gate and land in
  **Needs review** (safe by design), but a borderline call can mis-sort.
- **Employee matching is name-substring on display names.** Short names can collide
  ("Amit" ⊂ "Amitabh"). No per-employee email allowlist yet.
- **Priority/deadline accuracy is Gemini-dependent** in the digest; the bullet text is
  the source of truth even if a label is off.
- **Digest bullets only see the first 4,000 chars of a thread.** A fact buried deep
  in an old quoted reply won't reach the bullets. Accepted trade-off: the newest
  message sits at the top of plain-text reply chains.
- **No automated tests.** Verification is manual (dry-runs + isolation scripts).
- **No alerting.** If the refresh token expires or Gemini errors, you find out by
  reading the logs (symptom + fix in CLAUDE.md's Operational gotchas).

---

## 10. Gotchas / lessons learned

- **A failing email is a money pit if it stays unread.** 2026-06-22 20:06 UTC: one
  email's Gemini call exceeded the 60s read timeout; the error path skipped both
  `move_message` and the seen-file, so the per-minute cron refetched and re-sent it
  363 times over ~12 hours until the email was manually deleted. Google bills
  timed-out requests server-side → ~$45 in one day (the June billing spike, 417%
  MoM). Diagnosis came entirely from `inbox-cycle.log` (all 363 errors shared one
  message_id). Fix: fail → "Needs review" + mark seen, plus input caps. Any future
  retry logic must have a retry cap and an eventual dead-letter destination.
- **Duplicated facts drift.** It happened twice: the digest schedule (docs said 8 AM
  while the droplet ran 10 AM) and the employee list (CLAUDE.md claimed Vikram was
  excluded; `config/employees.py` includes him). Every fact now has exactly one home
  — see the documentation-ownership rules in the parent `../CLAUDE.md`. When you
  change the droplet cron, update CLAUDE.md in the *same* session.
- **Don't `git restore` and forget the droplet** — Round 2 was reverted locally, but
  the cron change had already been applied to the droplet. Local revert ≠ droplet
  revert. They drift independently.
- **The classifier will eat the digest** if not carved out — it ran once, classified
  the first digest as "Normal priority," and moved it out of the Inbox. Hence the
  `SKIP_SUBJECT_PREFIX` carve-out in `run_inbox_cycle.py`. Keep it.
- **"In To" is not "addressed to him"** — his address is in To on virtually every
  email to his own mailbox. Personalization must be judged by the salutation/body.
- **Outlook for Windows uses Word's HTML engine** — no JS, no custom fonts, unreliable
  border-radius/textarea. Any email HTML must be inline-styled tables only. This is
  why the dashboard email failed.
- **Repo must stay public** for the droplet's credential-less `git pull`. If it's ever
  flipped private, the pull 404s with `could not read Username for 'https://github.com'`.

---

## Commit-history orientation (most recent first)

- `0dd0c67` Digest: truncate summarizer body to 4000 chars before Gemini
- `c264642` Classifier: skip Gemini for deterministic sender types
- `1951480` Digest: show received date/time (IST) under each email
- `dfd6710` CLAUDE.md: fix digest schedule drift, point deployment refs at skills/
- `b4a740b` Classifier: recognize booked-trip vs promotional travel emails
- `6590705` Raise digest default --limit from 100 to 200
- `bda0b64` Bump digest cadence to 3x daily (8 AM / 12 PM / 4 PM IST)  ← later shifted
  to 10 AM via droplet cron only; not reflected in that commit
- `b3789af` Add daily inbox-summary digest
- `796aa97` Add 'what needs me' section to CLAUDE.md; remove NEXT_STEPS.md
- `874a196` Drop GitHub Actions, target VPS + cron for deployment
- `b689c75` Switch to cert-based confidential client auth
- `53122f0` Initial commit: WAT email classifier
