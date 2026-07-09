#!/usr/bin/env python3
"""One-time helper to mint a Google OAuth refresh token for Gmail + Calendar.

Prereqs:
  1. In Google Cloud Console, create an OAuth 2.0 Client ID of type "Desktop app".
  2. Enable the Gmail API and Google Calendar API for the project.
  3. Put the client id/secret in your environment or pass them below.

Usage:
  pip install ".[google]"
  GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python scripts/google_auth.py

It opens a browser (or prints a URL), you approve, and it prints the
GOOGLE_REFRESH_TOKEN to paste into your .env.
"""
from __future__ import annotations

import os
import sys

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def main() -> int:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not (client_id and client_secret):
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.", file=sys.stderr)
        return 1
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install deps: pip install \".[google]\"", file=sys.stderr)
        return 1

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    try:
        creds = flow.run_local_server(port=0, prompt="consent")
    except Exception:
        creds = flow.run_console()  # headless fallback

    print("\n" + "=" * 60)
    print("Success! Add this to your .env:")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
