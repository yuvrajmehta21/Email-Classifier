# Email Classifier — Project Notes

Shared WAT-framework rules, git policy, and deployment patterns live in the parent [../CLAUDE.md](../CLAUDE.md). This file holds only project-specific facts.

## What this project does

Two scheduled jobs run against Vikram's Outlook mailbox:

1. **Per-minute classifier** — polls unread mail, classifies each with Gemini 2.5 Flash into one of 7 buckets (Addressed to me / Urgent / Normal priority / Needs review / Promotions / Miscellaneous / BBG/Roxy), and moves it to the matching folder. Direct replacement for a previously-deployed n8n workflow. See [workflows/classify_inbox.md](workflows/classify_inbox.md).

2. **Daily 8 AM IST digest** — reads emails Vikram has moved back into his Inbox (his curated must-deal-with set), summarizes each in 3 bullets via Gemini, groups by which listed employee the email involves, and sends the digest to Vikram from his own mailbox. See [workflows/daily_summary.md](workflows/daily_summary.md).

## Auth pattern (Microsoft Graph)

Confidential client via certificate, not client secret. This is forced by the client tenant's policy that blocks client secrets across the whole tenant.

The pattern: a self-signed cert is uploaded to the Azure app registration; locally, the private key sits in `.secrets/concept-classifier.key` referenced by `MS_CERT_PRIVATE_KEY_PATH` in `.env`. The cert authenticates the *app*. A refresh token (`MS_REFRESH_TOKEN`, populated by `tools/outlook_auth.py --bootstrap`) represents Vikram's consent to act on his mailbox.

Why this is more than cosmetic: **public-client refresh tokens rotate and invalidate on every use** (Microsoft enforces single-use for public clients as a security default). Confidential-client refresh tokens are reusable — which is what makes the cloud cron work without state juggling. If you ever consider "just use a public client and skip the cert," the answer is no — we already tried, the cron breaks after the first run.

Full Azure setup steps in [workflows/outlook_setup.md](workflows/outlook_setup.md).

## Deployment

Runs as a `cron` job on a DigitalOcean droplet (Ubuntu 24.04, $4/month, fires every minute via `* * * * *` wrapped in `flock`). The droplet pulls code from this public GitHub repo; secrets live only on the droplet (scp'd from local), never in the repo.

Standard deployment pattern is documented in the parent [../CLAUDE.md](../CLAUDE.md). Project-specific facts:

- VPS IP: `167.71.232.223` (DigitalOcean)
- Project path on VPS: `/root/Email-Classifier`
- Cron logs on the VPS:
  - `/root/inbox-cycle.log` — per-minute classifier
  - `/root/daily-summary.log` — 8 AM IST digest
- Cron lines on the VPS:
  - `* * * * *` (every minute) — classifier
  - `30 2 * * *` if droplet TZ is UTC, or `0 8 * * *` if droplet TZ is IST — daily digest at 8 AM IST. Verify with `ssh root@167.71.232.223 date` before installing.
- Local secrets: `.env` + `.secrets/concept-classifier.key`

To watch cron in real time:
- Classifier: `ssh root@167.71.232.223 'tail -f /root/inbox-cycle.log'`
- Digest: `ssh root@167.71.232.223 'tail -f /root/daily-summary.log'`

## What needs me (vs. what runs on its own)

The droplet runs the entire pipeline autonomously. My Mac being on, off, online, or offline has zero effect on whether emails get classified. The only things that require me to do something:

- **Code changes** — edit on Mac, `git push`, then `ssh root@167.71.232.223 'cd /root/Email-Classifier && git pull'`. The next cron tick uses the new code. No restart needed.
- **Secret changes** (e.g., new refresh token after a re-bootstrap) — `scp .env root@167.71.232.223:/root/Email-Classifier/.env`. Same for `.secrets/concept-classifier.key` if the cert ever changes. Next cron tick uses the new values.
- **Refresh token re-bootstrap** — possibly once every few months, possibly never. Symptom: cron starts failing with auth errors in the log. Fix: `python tools/outlook_auth.py --bootstrap` on Mac (Vikram signs in once), then scp `.env` to droplet.
- **Pausing the cron** — `ssh root@167.71.232.223 'crontab -r'` removes the schedule. To restore, re-install the cron entry.
- **Tuning the classifier** — same as code changes (edit `config/domain_lists.py` or the prompt in `tools/classify_with_gemini.py`, push, pull on droplet).

What does NOT need me:
- The Mac being open or awake
- The Mac being connected to the internet
- Me logging into the droplet to "check on it"
- Anything related to GitHub at runtime — after `git clone`, the droplet doesn't talk to GitHub again until I manually `git pull`
- Microsoft refresh token expiry, *unless and until* it actually expires

## Tuning behavior

Knobs:
- **Domain lists** ([config/domain_lists.py](config/domain_lists.py)) — Buyer / Internal / Promotional / Miscellaneous / BBG-Roxy domain assignments. Used by the per-minute classifier.
- **Classifier prompt** (`SYSTEM_PROMPT` inside [tools/classify_with_gemini.py](tools/classify_with_gemini.py)) — keep the confidence-rules block in sync with the `<= 0.6 → Needs review` gate in [tools/apply_label.py](tools/apply_label.py).
- **Employee list** ([config/employees.py](config/employees.py)) — names whose emails get grouped in the daily digest. Vikram is intentionally excluded.
- **Summarizer prompt** (`SYSTEM_PROMPT` inside [tools/summarize_with_gemini.py](tools/summarize_with_gemini.py)) — controls the 3-bullet style of the daily digest.

All edits follow the same flow: edit locally, commit, push, then `git pull` on the VPS. No restart needed; the next cron tick picks up the change.

## Operational gotchas

- **Refresh token may eventually expire** (Microsoft uses a 90-day sliding window for confidential client refresh tokens; it should keep extending as long as the job runs daily, but isn't guaranteed forever). When it does, cron starts failing with auth errors. Fix: re-run `python tools/outlook_auth.py --bootstrap` locally (Vikram signs in once), then scp the updated `.env` to the droplet.
- **Don't re-enable the old n8n workflow.** Both systems racing against the same inbox will double-process emails.
- **The `Inbox Automation.json` file** is a historical artifact — the original n8n workflow export, kept for reference. Not used at runtime.
