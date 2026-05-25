# Outlook Business Account Setup — One-Time

## Why this exists
The client's Outlook is a Microsoft 365 **business** account. Most M365 tenants block unverified third-party OAuth apps (this is exactly what tripped n8n). The fix: register **our own** Azure AD app inside the client's tenant and have an admin grant consent once. After that the routine uses a refresh token directly against Microsoft Graph, with no third-party connector in the trust path.

This is a one-time setup. After it's done, the `MS_REFRESH_TOKEN` in `.env` (and in the cloud routine's environment) keeps working until it's revoked.

---

## Step 1 — Register the app in the client's Azure AD tenant

The client's IT/admin does this in the Azure portal (or you do it on a screen-share):

1. **Azure Portal → Microsoft Entra ID → App registrations → New registration**
2. **Name**: `Concept Clothing Inbox Classifier` (or similar — internal-only label)
3. **Supported account types**: *Accounts in this organizational directory only* (single tenant)
4. **Redirect URI**: choose **Web** and set `http://localhost:8400/callback`
5. Click **Register**

After registration, copy two values:
- **Application (client) ID** → goes in `.env` as `MS_CLIENT_ID`
- **Directory (tenant) ID** → goes in `.env` as `MS_TENANT_ID`

## Step 2 — Configure API permissions

Still inside the new app registration:

1. **API permissions → Add a permission → Microsoft Graph → Delegated permissions**
2. Add: `Mail.ReadWrite`, `Mail.Read`, `User.Read`, `offline_access`
3. Click **Grant admin consent for {tenant}**. **This is the step that makes the difference vs. n8n.** A directory admin must click this — it's not something Vikram can do as a regular user.

If "Grant admin consent" is greyed out, the person doing the setup isn't an admin. Hand off to whoever in the client's IT can do it.

## Step 3 — (Optional) Client secret

If you registered the app as confidential (most defaults), you'll also need:

1. **Certificates & secrets → New client secret**
2. Copy the **Value** (not the ID — Azure shows the value once and never again) → `.env` as `MS_CLIENT_SECRET`

If you skip this, `outlook_auth.py` will run in PublicClientApplication mode, which works for the device-code / browser-redirect flows we use here.

## Step 4 — Bootstrap the refresh token (on the laptop, once)

```bash
cd "Email Classifier"
pip install -r requirements.txt
# Make sure MS_TENANT_ID and MS_CLIENT_ID (and MS_CLIENT_SECRET if applicable) are in .env
python tools/outlook_auth.py --bootstrap
```

What happens:
1. Browser opens to Microsoft's sign-in page.
2. **Vikram signs in with his Outlook business account** (not yours — the routine acts on his mailbox).
3. Microsoft redirects to `http://localhost:8400/callback` with an auth code.
4. The script exchanges that code for a refresh token and writes `MS_REFRESH_TOKEN` to `.env`.

Verify:
```bash
python tools/outlook_auth.py --print-token | head -c 40
```
A long base64-ish string means it worked. An error means refresh-token exchange failed — re-run `--bootstrap`.

## Step 5 — Copy secrets to the cloud routine

The cloud routine doesn't see the laptop's `.env`. When you create the routine via the `/schedule` skill, set its environment to include:

```
MS_TENANT_ID=<from .env>
MS_CLIENT_ID=<from .env>
MS_CLIENT_SECRET=<from .env, if set>
MS_REFRESH_TOKEN=<from .env>
GEMINI_API_KEY=<from .env>
```

## Step 6 — Verify end-to-end on the laptop before scheduling

```bash
python tools/outlook_fetch_unread.py --limit 3
python tools/run_inbox_cycle.py --dry-run --limit 3
# Then a real run with one test email:
python tools/run_inbox_cycle.py --limit 1
```
Confirm in Outlook that the message landed in the expected folder.

---

## Failure modes & what they mean

- **"AADSTS65001: The user or administrator has not consented"** → Step 2's admin consent wasn't actually granted. Re-do Step 2.
- **"AADSTS50020: User account from external provider not authorized"** → Vikram signed in with the wrong account (e.g., a personal Microsoft account instead of his business one).
- **"AADSTS700016: app was not found in this tenant"** → `MS_TENANT_ID` is wrong, or the app was registered in a different tenant than Vikram's account.
- **`invalid_grant` on refresh** → token revoked (admin disabled, password change, conditional-access policy). Re-run `--bootstrap`.
- **Per-message `403 Forbidden`** → the consented scopes are missing `Mail.ReadWrite`. Re-check Step 2.

## What we are NOT doing (and why)

- **No application-permission flow with client credentials.** That would let the routine act on *any* mailbox in the tenant, which is overprivileged and harder to get admin consent for.
- **No IMAP / app passwords.** Most M365 business tenants have basic auth disabled by policy.
- **No third-party connectors.** That's what failed with n8n.
