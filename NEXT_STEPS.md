# Next Steps

Deploy the classifier as a 1-minute cron job on a small VPS.

## Why a VPS, not GitHub Actions / Claude routines / n8n

- **GitHub Actions cron is unreliable for minute-level intervals.** GitHub doesn't guarantee on-time firing of scheduled workflows, especially `*/5` or faster. We tried; the scheduler simply did not fire our schedule. No setting or pricing tier fixes this.
- **Claude routines have a 1-hour minimum cron.** Too slow for inbox triage.
- **n8n was expensive per workflow call.** That was the reason to migrate off it.

A $4-6/month Linux VPS with plain cron is the boring, reliable answer: cron on a Unix box fires exactly when you tell it to.

## One-time setup (this is what's left to do)

- [ ] **Create a DigitalOcean account** (or any VPS provider — Hetzner / Linode / Vultr are all fine). New users typically get a credit that covers the first few months.
- [ ] **Create a basic Ubuntu droplet** — cheapest tier ($4/month "Basic" with 1 GB RAM is plenty).
- [ ] **SSH in** and run the setup commands (see below — git clone, install python deps, etc.).
- [ ] **scp the secrets** from your laptop to the droplet: the `.env` file and the `.secrets/concept-classifier.key` file.
- [ ] **Add the cron entry** — one line in `crontab -e`.
- [ ] **Watch the first few runs** via `tail -f` on the log file.

## Cron entry

```cron
* * * * * /usr/bin/flock -n /tmp/inbox-cycle.lock /home/<user>/Email-Classifier/.venv/bin/python /home/<user>/Email-Classifier/tools/run_inbox_cycle.py >> /home/<user>/inbox-cycle.log 2>&1
```

`flock` prevents two cron-fired runs from stepping on each other if one happens to run long (>60s). Should be rare since runs are typically 5-15s.

## Maintenance

- [ ] **Tune after ~1 week** — review the "Needs review" folder with Vikram. Promote recurring misclassifications into [config/domain_lists.py](config/domain_lists.py), commit, push. On the droplet: `cd Email-Classifier && git pull`. Cron picks up the change on the next tick.
- [ ] **Re-bootstrap if Microsoft eventually expires the refresh token (~90 day sliding window)** — runs start failing. Fix: re-run `python tools/outlook_auth.py --bootstrap` on your laptop (Vikram signs in once), then scp the updated `.env` to the droplet.

## What was rolled back / removed

- `.github/workflows/inbox-cycle.yml` — the failed GitHub Actions cron approach.
- The dual-key support in `outlook_auth.py` (`MS_CERT_PRIVATE_KEY` inline content) — only existed for GitHub Secrets, no longer needed.
- The corresponding GitHub repository secrets should be deleted manually (Settings → Secrets and variables → Actions → delete each one).
