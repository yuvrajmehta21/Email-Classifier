# Daily Inbox Summary — 3x daily (8 AM / 12 PM / 4 PM IST) digest

## Objective
Three times a day, read the emails Vikram has marked-read-and-kept (or moved back) in his Inbox, summarize each in 3 bullets, group by which listed employee the email involves, and email the digest to Vikram from his own mailbox.

## Required inputs (from `.env`)
- `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CERT_THUMBPRINT`, `MS_CERT_PRIVATE_KEY_PATH`, `MS_REFRESH_TOKEN` — Microsoft Graph auth. The refresh token must have been bootstrapped after `Mail.Send` was added to `outlook_auth.SCOPES`.
- `GEMINI_API_KEY` — same key the classifier uses.

## Tool sequence

```
python tools/run_daily_summary.py
```

Flags:
- `--dry-run` — build the digest, don't send. The full HTML body is in the JSON output for inspection.
- `--limit N` — cap fetched messages (default 100).

Per cycle:
1. `tools/outlook_fetch_read.py` — `GET /me/mailFolders/{SOURCE_FOLDER_ID}/messages?$filter=isRead eq true`, with `Prefer: outlook.body-content-type="text"` and `body` in `$select` so we get the full plain-text body.
2. `tools/normalize_email.py` — flatten Graph fields (body is then overwritten with the full body from the raw Graph message).
3. `tools/categorize_by_employee.py` — assign the email to zero, one, or more employee sections.
4. `tools/summarize_with_gemini.py` — three one-line bullets ranked by urgency.
5. Build HTML grouped by employee + "Other reads" section at the bottom.
6. `tools/outlook_send_mail.py` — `POST /me/sendMail`, recipient is `VIKRAM_EMAIL`. Sender is implicit (the authenticated user is Vikram), so it arrives in his Inbox "from himself."

## Categorization rules

1. If the first non-empty line of the body starts with `Hi <name>`, `Hello <name>`, or `Dear <name>` and `<name>` matches a listed employee (case-insensitive substring), file under that employee only.
2. Else, file under every listed employee whose name appears (case-insensitive substring) in the sender's display name or any To display name. CC is excluded — being CC'd on a long thread would otherwise pull a person into the digest under every reply on that thread.
3. Else, file under "Other reads".

Employee list (see [config/employees.py](../config/employees.py)): `Gulshan`, `Rashmi`, `Pradeep`, `Amit`, `Srivastava`, `Neetu`, `Pankaj`, `Indra`, `Bharti`, `Piyush`, `Shaji`, `Vikram Mehta`. Vikram is matched as full name (`Vikram Mehta`) rather than just `Vikram` to keep the substring tight; emails whose display name shows only "Vikram" won't match.

## Expected output

JSON to stdout, plus an email to Vikram (unless `--dry-run`):

```json
{
  "started_at": "...",
  "date_ist": "2026-05-27",
  "fetched": 14,
  "processed": 14,
  "errors_count": 0,
  "sent": true,
  "subject": "Daily Inbox Summary — 2026-05-27",
  "html_body": null,
  "errors": []
}
```

Exit code 0 on success, 1 if any per-message error occurred (the digest is still sent for the rest).

## Edge cases & known behavior

- **Gemini returns invalid JSON** — `summarize_with_gemini.summarize` falls back to `["[summary unavailable]"]`. The digest still renders.
- **Zero read emails in Inbox** — no email is sent. JSON output shows `processed: 0`, `sent: false`.
- **Short first names collide** — matching is case-insensitive substring of display names, so `Amit` could match `Amitabh`. Acceptable for v1; add an email-address allowlist later if false positives surface.
- **Email matches multiple employees** — appears under each matching section in the HTML. If the user said `Hi Pradeep` in the body, only Pradeep gets it (the greeting rule pins routing).
- **The same email appears on consecutive days** — by design. Vikram's pattern is to keep emails in the Inbox until handled; he sees them in the digest until he moves them out.

## Scheduling

Runs as a `cron` job on the same droplet as the per-minute classifier:
- Three fires per day at 8 AM, 12 PM, and 4 PM IST. If the droplet's clock is UTC, cron is `30 2,6,10 * * *` (02:30, 06:30, 10:30 UTC). If the clock is IST, cron is `0 8,12,16 * * *`. Verify with `ssh root@167.71.232.223 date`.
- Wrapped in `flock` with a separate lock file (`/tmp/daily-summary.lock`) so it doesn't block the per-minute classifier.
- Logs to `/root/daily-summary.log` on the droplet.

Cron line (UTC droplet):
```
30 2,6,10 * * * cd /root/Email-Classifier && /usr/bin/flock -n /tmp/daily-summary.lock /root/Email-Classifier/.venv/bin/python tools/run_daily_summary.py >> /root/daily-summary.log 2>&1
```

## Verification

```bash
# 1. Auth has Mail.Send (after re-bootstrapping):
python tools/outlook_auth.py --print-token | head -c 40

# 2. Fetch a few read messages:
python tools/outlook_fetch_read.py --limit 3

# 3. Build the digest without sending:
python tools/run_daily_summary.py --dry-run --limit 3

# 4. Send a real digest with a tiny cap:
python tools/run_daily_summary.py --limit 1
```

## First-time deployment checklist

1. Add `Mail.Send` to `SCOPES` in `tools/outlook_auth.py` (already done — verify on `main`).
2. Re-bootstrap locally: `python tools/outlook_auth.py --bootstrap` — Vikram signs in once.
3. `scp .env root@167.71.232.223:/root/Email-Classifier/.env`
4. `git push` locally; `git pull` on the droplet.
5. Verify droplet timezone (`ssh root@167.71.232.223 date`), then add the cron line above (or the IST variant).
6. Watch the first scheduled run: `ssh root@167.71.232.223 'tail -f /root/daily-summary.log'`.

## Updating the employee list
Edit [config/employees.py](../config/employees.py), commit, push, `git pull` on the droplet. Next 8 AM cycle picks up the change. No restart needed.

## Updating the summarizer prompt
`SYSTEM_PROMPT` inside [tools/summarize_with_gemini.py](../tools/summarize_with_gemini.py). Output schema must keep `{"bullets": [...]}` shape — the orchestrator depends on the list.
