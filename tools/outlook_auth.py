#!/usr/bin/env python3
"""
outlook_auth.py — Microsoft Graph access-token helper for Vikram's mailbox.

Authenticates as a confidential client using a certificate (not a secret —
the tenant policy blocks client secrets). Confidential-client refresh tokens
can be reused, which is what lets the GitHub Actions cron job re-use the
same MS_REFRESH_TOKEN across runs without rotation invalidating it.

Two modes:
  --bootstrap    One-time interactive sign-in. Opens the browser, captures
                 the OAuth code, exchanges it for a refresh token, writes it
                 to .env as MS_REFRESH_TOKEN. Run this once on the laptop
                 after the cert has been uploaded to Azure.

  --print-token  Use the stored refresh token to mint a fresh access token
                 and print it to stdout. Used by the other tools and by the
                 GitHub Actions cron.

Required env vars (in .env):
  MS_TENANT_ID
  MS_CLIENT_ID
  MS_CERT_THUMBPRINT       — SHA-1 thumbprint of the cert uploaded to Azure
  MS_CERT_PRIVATE_KEY_PATH — path to the .key file (relative to project root)
  MS_REFRESH_TOKEN         — populated by --bootstrap, used by --print-token
"""

from __future__ import annotations

import argparse
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import msal
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
TENANT_ID = os.getenv("MS_TENANT_ID", "")
CERT_THUMBPRINT = os.getenv("MS_CERT_THUMBPRINT", "").replace(":", "").replace(" ", "").upper()
CERT_PRIVATE_KEY_PATH = os.getenv("MS_CERT_PRIVATE_KEY_PATH", "")
REFRESH_TOKEN = os.getenv("MS_REFRESH_TOKEN", "")

REDIRECT_PORT = 8400
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = ["Mail.ReadWrite", "Mail.Read", "Mail.Send", "User.Read"]
# Do NOT add offline_access here — MSAL injects it automatically and rejects
# it if passed explicitly.

AUTHORITY = lambda: f"https://login.microsoftonline.com/{TENANT_ID}"


def _load_private_key() -> str:
    if not CERT_PRIVATE_KEY_PATH:
        sys.exit("MS_CERT_PRIVATE_KEY_PATH must be set in .env (path to the .key file).")
    path = Path(CERT_PRIVATE_KEY_PATH)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        sys.exit(f"Private key file not found: {path}")
    return path.read_text()


def _build_app() -> msal.ConfidentialClientApplication:
    if not CLIENT_ID or not TENANT_ID:
        sys.exit("MS_CLIENT_ID and MS_TENANT_ID must be set in the environment.")
    if not CERT_THUMBPRINT:
        sys.exit("MS_CERT_THUMBPRINT must be set (40-char SHA-1 hex of the uploaded cert).")

    credential = {
        "private_key": _load_private_key(),
        "thumbprint": CERT_THUMBPRINT,
    }
    return msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY(), client_credential=credential
    )


def bootstrap() -> None:
    """One-time interactive flow. Captures refresh token, writes to .env."""
    app = _build_app()
    state = secrets.token_urlsafe(16)
    auth_url = app.get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state,
        prompt="select_account",
    )

    received: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            received["code"] = params.get("code", [""])[0]
            received["state"] = params.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"You can close this tab.")

        def log_message(self, *_):  # silence default access log
            pass

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    print(f"Opening browser for sign-in. Listening on {REDIRECT_URI}")
    webbrowser.open(auth_url)

    while "code" not in received:
        pass

    if received.get("state") != state:
        sys.exit("OAuth state mismatch — aborting. Try --bootstrap again.")
    if not received.get("code"):
        sys.exit("No authorization code received.")

    result = app.acquire_token_by_authorization_code(
        received["code"], scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    if "refresh_token" not in result:
        sys.exit(f"No refresh token in response: {result}")

    set_key(str(ENV_PATH), "MS_REFRESH_TOKEN", result["refresh_token"])
    print(f"Wrote MS_REFRESH_TOKEN to {ENV_PATH}")


def get_access_token() -> str:
    """Mint a fresh access token from the stored refresh token."""
    if not REFRESH_TOKEN:
        sys.exit("MS_REFRESH_TOKEN not set. Run: python tools/outlook_auth.py --bootstrap")
    app = _build_app()
    result = app.acquire_token_by_refresh_token(REFRESH_TOKEN, scopes=SCOPES)
    if "access_token" not in result:
        sys.exit(f"Token refresh failed: {result}")
    # Confidential-client refresh tokens are reusable, so even if Microsoft
    # returns a new one, the old one stays valid. Persist the newer one
    # locally as a convenience, but only if we can write to .env (skipped in CI).
    new_rt = result.get("refresh_token")
    if new_rt and new_rt != REFRESH_TOKEN and ENV_PATH.exists():
        set_key(str(ENV_PATH), "MS_REFRESH_TOKEN", new_rt)
    return result["access_token"]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bootstrap", action="store_true")
    g.add_argument("--print-token", action="store_true")
    args = ap.parse_args()

    if args.bootstrap:
        bootstrap()
    else:
        print(get_access_token())


if __name__ == "__main__":
    main()
