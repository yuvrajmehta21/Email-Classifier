#!/usr/bin/env python3
"""
outlook_auth.py — Microsoft Graph access-token helper for Vikram's mailbox.

Two modes:
  --bootstrap    One-time interactive sign-in. Opens the browser, captures the
                 OAuth code, exchanges it for a refresh token, writes it to .env
                 as MS_REFRESH_TOKEN. Run this once on the laptop after the
                 client's tenant admin has granted consent.

  --print-token  Use the stored refresh token to mint a fresh access token and
                 print it to stdout. Used by the other tools and by the cloud
                 routine.

Tenant: the client's Azure AD tenant ID goes in MS_TENANT_ID. Use the tenant
GUID, not "common" — admin consent is per-tenant, and pinning the tenant
prevents a stray personal-account login from succeeding.
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
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")  # optional — only needed for confidential apps
TENANT_ID = os.getenv("MS_TENANT_ID", "")
REFRESH_TOKEN = os.getenv("MS_REFRESH_TOKEN", "")

REDIRECT_PORT = 8400
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = ["Mail.ReadWrite", "Mail.Read", "User.Read"]
# Do NOT add offline_access here — MSAL injects it automatically and rejects
# it if passed explicitly. The refresh token comes back as long as the app
# registration has offline_access among its granted delegated permissions.

AUTHORITY = lambda: f"https://login.microsoftonline.com/{TENANT_ID}"


def _build_app() -> msal.ClientApplication:
    if not CLIENT_ID or not TENANT_ID:
        sys.exit("MS_CLIENT_ID and MS_TENANT_ID must be set in .env")
    if CLIENT_SECRET:
        return msal.ConfidentialClientApplication(
            CLIENT_ID, authority=AUTHORITY(), client_credential=CLIENT_SECRET
        )
    return msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY())


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

    # handle_request blocks the worker thread; wait for it to set received[]
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
    # Microsoft sometimes rotates the refresh token — persist if so.
    new_rt = result.get("refresh_token")
    if new_rt and new_rt != REFRESH_TOKEN:
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
