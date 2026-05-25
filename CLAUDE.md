# Email Classifier — Project Notes

Shared WAT-framework rules, git policy, and deployment patterns live in the parent [../CLAUDE.md](../CLAUDE.md). This file holds only project-specific facts.

## What this project does

Polls Vikram's Outlook business mailbox via Microsoft Graph every minute, classifies each unread email with Gemini 2.5 Flash into one of 7 buckets (Addressed to me / Urgent / Normal priority / Needs review / Promotions / Miscellaneous / BBG/Roxy), and moves it to the matching folder. Direct replacement for a previously-deployed n8n workflow.

See [workflows/classify_inbox.md](workflows/classify_inbox.md) for the per-cycle pipeline.

## Auth pattern (Microsoft Graph)

Confidential client via certificate, not client secret. This is forced by the client tenant's policy that blocks client secrets across the whole tenant.

The pattern: a self-signed cert is uploaded to the Azure app registration; locally, the private key sits in `.secrets/concept-classifier.key` referenced by `MS_CERT_PRIVATE_KEY_PATH` in `.env`. The cert authenticates the *app*. A refresh token (`MS_REFRESH_TOKEN`, populated by `tools/outlook_auth.py --bootstrap`) represents Vikram's consent to act on his mailbox.

Why this is more than cosmetic: **public-client refresh tokens rotate and invalidate on every use** (Microsoft enforces single-use for public clients as a security default). Confidential-client refresh tokens are reusable — which is what makes the cloud cron work without state juggling. If you ever consider "just use a public client and skip the cert," the answer is no — we already tried, the cron breaks after the first run.

Full Azure setup steps in [workflows/outlook_setup.md](workflows/outlook_setup.md).

## Deployment

Runs as a `cron` job on a DigitalOcean droplet (Ubuntu 24.04, $4/month, fires every minute via `* * * * *` wrapped in `flock`). The droplet pulls code from this public GitHub repo; secrets live only on the droplet (scp'd from local), never in the repo.

Standard deployment pattern is documented in the parent [../CLAUDE.md](../CLAUDE.md). Project-specific facts:

- VPS IP: `167.71.232.223` (DigitalOcean, NYC region)
- Project path on VPS: `/root/Email-Classifier`
- Cron log: `/root/inbox-cycle.log` on the VPS
- Local secrets: `.env` + `.secrets/concept-classifier.key`

To watch cron in real time: `ssh root@167.71.232.223 'tail -f /root/inbox-cycle.log'`.

## Tuning behavior

Two knobs:
- **Domain lists** ([config/domain_lists.py](config/domain_lists.py)) — Buyer / Internal / Promotional / Miscellaneous / BBG-Roxy domain assignments. Edit, commit, push, then `git pull` on the VPS.
- **Classifier prompt** (`SYSTEM_PROMPT` inside [tools/classify_with_gemini.py](tools/classify_with_gemini.py)) — keep the confidence-rules block in sync with the `<= 0.6 → Needs review` gate in [tools/apply_label.py](tools/apply_label.py).

## Operational gotchas

- **Refresh token may eventually expire** (Microsoft uses a 90-day sliding window for confidential client refresh tokens; it should keep extending as long as the job runs daily, but isn't guaranteed forever). When it does, cron starts failing with auth errors. Fix: re-run `python tools/outlook_auth.py --bootstrap` locally (Vikram signs in once), then scp the updated `.env` to the droplet.
- **Don't re-enable the old n8n workflow.** Both systems racing against the same inbox will double-process emails.
- **The `Inbox Automation.json` file** is a historical artifact — the original n8n workflow export, kept for reference. Not used at runtime.
