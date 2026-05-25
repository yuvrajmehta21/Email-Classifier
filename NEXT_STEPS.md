# Next Steps

Path from "code written" to "running on cron in the cloud."

The Azure AD app already exists (registered during the n8n setup, in Vikram's tenant, with admin consent granted). We reuse it instead of registering a new one. The Gemini API key is already in `.env`.

## Setup

- [ ] **Pull credentials from the existing Azure app** — in the Azure Portal, open the app registration used for n8n and copy into `.env`:
  - `MS_TENANT_ID` ← Directory (tenant) ID
  - `MS_CLIENT_ID` ← Application (client) ID
  - `MS_CLIENT_SECRET` ← if the n8n app was confidential and you still have the secret value saved. If not, generate a new secret under **Certificates & secrets → New client secret** (doesn't affect n8n; the app can have multiple secrets).
- [ ] **Add our redirect URI to the existing app** — under **Authentication → Web → Redirect URIs**, *add* (don't replace) `http://localhost:8400/callback`. n8n's existing redirect URI keeps working. Only needed for the one-time bootstrap below; after that, the redirect URI is irrelevant.
- [ ] **Verify the app's delegated permissions include all four scopes** — `Mail.ReadWrite`, `Mail.Read`, `User.Read`, `offline_access`. If `Mail.ReadWrite` is missing (n8n may have only needed read), add it and have an admin re-click **Grant admin consent**. If all four are already there with consent granted, skip this step.
- [ ] **Bootstrap refresh token** — `.venv/bin/python tools/outlook_auth.py --bootstrap`. Vikram signs in once with his Outlook business account. Verify `MS_REFRESH_TOKEN` gets written to `.env`. (The n8n refresh token can't be reused — it was minted for n8n's client config.)

## Local verification (~10 min)

- [ ] **Fetch smoke test** — `.venv/bin/python tools/outlook_fetch_unread.py --limit 3` returns real unread messages.
- [ ] **Dry-run pipeline** — `.venv/bin/python tools/run_inbox_cycle.py --dry-run --limit 3`. Inspect labels and confidences in the JSON summary.
- [ ] **Live test** — send Vikram one email of each obvious bucket (urgent, promo, BBG/Roxy). Run `--limit 5`. Verify each lands in the right Outlook folder.

## Cutover from n8n

- [ ] **Disable the n8n workflow** before scheduling the routine, so both don't fight over the same inbox.

## Production

- [ ] **Create the routine** via `/schedule` — cron `* * * * *` (every minute, matching the n8n workflow), command `python tools/run_inbox_cycle.py`. Copy all `.env` values into the routine's environment.
- [ ] **Watch first ~3 runs** in `/schedule` list output for errors. Spot-check Outlook to confirm new mail gets sorted with the laptop off.

## Maintenance

- [ ] **Tune after ~1 week** — review the "Needs review" folder with Vikram. Promote recurring misclassifications into `config/domain_lists.py`.
