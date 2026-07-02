# Email Classifier — Project Notes

Shared WAT-framework rules and git policy live in the parent [../CLAUDE.md](../CLAUDE.md); deployment and scheduling procedures live in [../skills/](../skills/). This file holds only project-specific facts.

## What this project does

Two scheduled jobs run against Vikram's Outlook mailbox:

1. **Per-minute classifier** — polls unread mail, classifies each with Gemini 2.5 Flash into one of 7 buckets (Addressed to me / Urgent / Normal priority / Needs review / Promotions / Miscellaneous / BBG/Roxy), and moves it to the matching folder. Direct replacement for a previously-deployed n8n workflow. See [workflows/classify_inbox.md](workflows/classify_inbox.md).

2. **Daily digest (10 AM IST)** — reads emails Vikram has moved back into his Inbox (his curated must-deal-with set), summarizes each in 3 bullets via Gemini, groups by which listed employee the email involves, and sends the digest to Vikram from his own mailbox. See [workflows/daily_summary.md](workflows/daily_summary.md).

## Auth pattern (Microsoft Graph)

Confidential client via certificate, not client secret. This is forced by the client tenant's policy that blocks client secrets across the whole tenant.

The pattern: a self-signed cert is uploaded to the Azure app registration; locally, the private key sits in `.secrets/concept-classifier.key` referenced by `MS_CERT_PRIVATE_KEY_PATH` in `.env`. The cert authenticates the *app*. A refresh token (`MS_REFRESH_TOKEN`, populated by `tools/outlook_auth.py --bootstrap`) represents Vikram's consent to act on his mailbox.

Why this is more than cosmetic: **public-client refresh tokens rotate and invalidate on every use** (Microsoft enforces single-use for public clients as a security default). Confidential-client refresh tokens are reusable — which is what makes the cloud cron work without state juggling. If you ever consider "just use a public client and skip the cert," the answer is no — we already tried, the cron breaks after the first run.

Full Azure setup steps in [workflows/outlook_setup.md](workflows/outlook_setup.md).

## Deployment

Runs as a `cron` job on a DigitalOcean droplet (Ubuntu 24.04, $4/month, fires every minute via `* * * * *` wrapped in `flock`). The droplet pulls code from this public GitHub repo; secrets live only on the droplet (scp'd from local), never in the repo.

Standard deployment pattern is documented in [../skills/deployment-skill.md](../skills/deployment-skill.md). Project-specific facts:

- VPS IP: `167.71.232.223` (DigitalOcean)
- Project path on VPS: `/root/Email-Classifier`
- Cron logs on the VPS:
  - `/root/inbox-cycle.log` — per-minute classifier
  - `/root/daily-summary.log` — daily digest
- Cron lines on the VPS:
  - `* * * * *` (every minute) — classifier
  - `30 4 * * *` if droplet TZ is UTC, or `0 10 * * *` if droplet TZ is IST — digest once daily at 10 AM IST. Verify with `ssh root@167.71.232.223 date` before installing. (Droplet currently runs UTC with `30 4`.)
- Local secrets: `.env` + `.secrets/concept-classifier.key`

To watch cron in real time:
- Classifier: `ssh root@167.71.232.223 'tail -f /root/inbox-cycle.log'`
- Digest: `ssh root@167.71.232.223 'tail -f /root/daily-summary.log'`

## What needs me (vs. what runs on its own)

The droplet runs the entire pipeline autonomously — the Mac's state (on/off/online) is irrelevant, and after the initial `git clone` the droplet never talks to GitHub until a manual `git pull`. Only these need a human; in every case the next cron tick picks up the change with no restart:

- **Code or tuning changes** — edit on Mac, commit, `git push`, then `ssh root@167.71.232.223 'cd /root/Email-Classifier && git pull'`.
- **Secret changes** — `scp .env root@167.71.232.223:/root/Email-Classifier/.env`. Same for `.secrets/concept-classifier.key` if the cert ever changes.
- **Refresh token re-bootstrap** — see Operational gotchas below.
- **Pausing the cron** — `ssh root@167.71.232.223 'crontab -r'` removes the schedule. To restore, re-install the cron entry.

## Tuning behavior

Knobs:
- **Domain lists** ([config/domain_lists.py](config/domain_lists.py)) — Buyer / Internal / Promotional / Miscellaneous / BBG-Roxy domain assignments. Used by the per-minute classifier.
- **Classifier prompt** (`SYSTEM_PROMPT` inside [tools/classify_with_gemini.py](tools/classify_with_gemini.py)) — keep the confidence-rules block in sync with the `<= 0.6 → Needs review` gate in [tools/apply_label.py](tools/apply_label.py) and with the `DETERMINISTIC_SENDER_TYPES` short-circuit table in [tools/run_inbox_cycle.py](tools/run_inbox_cycle.py).
- **Employee list** ([config/employees.py](config/employees.py)) — 12 names whose emails get grouped in the daily digest. Vikram is included as the full name "Vikram Mehta".
- **Summarizer prompt** (`SYSTEM_PROMPT` inside [tools/summarize_with_gemini.py](tools/summarize_with_gemini.py)) — controls the 3-bullet style of the daily digest.

## Operational gotchas

- **Refresh token may eventually expire** (Microsoft uses a 90-day sliding window for confidential client refresh tokens; it should keep extending as long as the job runs daily, but isn't guaranteed forever). When it does, cron starts failing with auth errors. Fix: re-run `python tools/outlook_auth.py --bootstrap` locally (Vikram signs in once), then scp the updated `.env` to the droplet.
- **Don't re-enable the old n8n workflow.** Both systems racing against the same inbox will double-process emails.
- **The `Inbox Automation.json` file** is a historical artifact — the original n8n workflow export, kept for reference. Not used at runtime.
