"""SMTP email delivery via a Gmail App Password.

Simplest, most durable way to email the brief: no OAuth, no verification, no
token expiry. Requires 2-Step Verification on the Google account and a 16-char
App Password (https://myaccount.google.com/apppasswords).

Env:
  SMTP_APP_PASSWORD  the 16-char app password (spaces are stripped)
  SMTP_USER          the Gmail address to send from (defaults to the first
                     BRIEF_RECIPIENT; must be the account the app password
                     belongs to)
  BRIEF_RECIPIENT    where to send — one or more, comma-separated
                     (defaults to SMTP_USER)
  SMTP_HOST          default smtp.gmail.com
  SMTP_PORT          default 465 (SSL)

Degrades gracefully: returns False if not configured.
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText

from ..config_loader import env
from ..utils.logging import get_logger

log = get_logger()


def recipients(raw: str | None = None) -> list[str]:
    """Split a comma-separated recipient string into addresses."""
    raw = raw if raw is not None else (env("BRIEF_RECIPIENT") or env("SMTP_USER"))
    return [a.strip() for a in (raw or "").split(",") if a.strip()]


def configured() -> bool:
    return bool(env("SMTP_APP_PASSWORD") and (env("SMTP_USER") or env("BRIEF_RECIPIENT")))


def send_email(subject: str, html_body: str, to: str | None = None) -> bool:
    password = env("SMTP_APP_PASSWORD")
    tos = recipients(to)
    user = env("SMTP_USER") or (tos[0] if tos else None)
    if not (password and user and tos):
        log.info("SMTP not configured; skipping SMTP send.")
        return False
    password = password.replace(" ", "")  # Gmail displays app passwords with spaces
    host = env("SMTP_HOST") or "smtp.gmail.com"
    port = int(env("SMTP_PORT") or "465")
    try:
        msg = MIMEText(html_body, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = ", ".join(tos)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx) as server:
            server.login(user, password)
            server.sendmail(user, tos, msg.as_string())
        log.info("Brief emailed via SMTP to %s", ", ".join(tos))
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("SMTP send failed: %s", exc)
        return False
