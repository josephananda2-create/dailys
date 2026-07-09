"""Shared Google OAuth credentials for Gmail + Calendar (read) and Gmail send.

Uses a refresh token stored in env (GOOGLE_REFRESH_TOKEN). Mint one with
`python scripts/google_auth.py`. Returns None if not configured or libs missing,
so callers can degrade gracefully.
"""
from __future__ import annotations

from ..config_loader import env
from ..utils.logging import get_logger

log = get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_credentials():
    client_id = env("GOOGLE_CLIENT_ID")
    client_secret = env("GOOGLE_CLIENT_SECRET")
    refresh_token = env("GOOGLE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        log.info("Google not configured (missing client id/secret/refresh token).")
        return None
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        log.warning("google-auth not installed; run `pip install .[google]`.")
        return None

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=_TOKEN_URI,
        scopes=SCOPES,
    )
    try:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    except Exception as exc:  # noqa: BLE001
        log.error("Google token refresh failed: %s", exc)
        return None
    return creds


def build_service(api: str, version: str):
    creds = get_credentials()
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build

        return build(api, version, credentials=creds, cache_discovery=False)
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to build Google %s service: %s", api, exc)
        return None
