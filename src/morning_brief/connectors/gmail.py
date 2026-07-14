"""Gmail connector: run gmail_search sources, and send the brief."""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from ..config_loader import Config, env
from ..models import Item, Source
from ..utils.dates import parse_dt
from ..utils.logging import get_logger
from ..utils.text import truncate
from .google_auth import build_service

log = get_logger()


def available() -> bool:
    return build_service("gmail", "v1") is not None


def fetch(source: Source, cfg: Config, limit: int = 15) -> list[Item]:
    """Run one gmail_search source and turn matching emails into Items."""
    query = source.query
    if not query:
        log.warning("Gmail '%s': no query, skipping.", source.name)
        return []
    service = build_service("gmail", "v1")
    if service is None:
        log.info("Gmail unavailable; skipping '%s'.", source.name)
        return []

    section = cfg.section_for(source.category)
    items: list[Item] = []
    try:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )
        for meta in resp.get("messages", []):
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=meta["id"], format="metadata",
                     metadataHeaders=["Subject", "From", "Date"])
                .execute()
            )
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "")
            snippet = msg.get("snippet", "")
            published = parse_dt(headers.get("date"))
            items.append(
                Item(
                    title=subject,
                    url=f"https://mail.google.com/mail/u/0/#inbox/{meta['id']}",
                    source_name=f"{source.name} ({_sender_name(sender)})",
                    category=source.category,
                    published=published,
                    summary=truncate(snippet, 750),
                    section=section,
                    region=source.region,
                    tags=source.tags,
                    reliability=source.reliability,
                    priority=source.priority,
                    kind="email",
                    extra={"from": sender},
                )
            )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"gmail search failed: {exc}") from exc

    log.info("Gmail '%s': %d emails", source.name, len(items))
    return items


def inbox_topics(cfg: Config, extra_query: str = "newer_than:2d", limit: int = 40) -> set[str]:
    """Lightweight scan of recent subjects → keyword set, used to boost same-topic news."""
    service = build_service("gmail", "v1")
    if service is None:
        return set()
    topics: set[str] = set()
    try:
        resp = service.users().messages().list(
            userId="me", q=f"category:primary OR category:updates {extra_query}", maxResults=limit
        ).execute()
        for meta in resp.get("messages", [])[:limit]:
            msg = service.users().messages().get(
                userId="me", id=meta["id"], format="metadata", metadataHeaders=["Subject"]
            ).execute()
            for h in msg.get("payload", {}).get("headers", []):
                if h["name"].lower() == "subject":
                    for w in h["value"].lower().split():
                        if len(w) > 4:
                            topics.add(w.strip(".,:;!?\"'()"))
    except Exception as exc:  # noqa: BLE001
        log.warning("inbox_topics scan failed: %s", exc)
    return topics


def send_email(subject: str, html_body: str, to: str | None = None) -> bool:
    service = build_service("gmail", "v1")
    if service is None:
        log.error("Cannot send email: Gmail not configured.")
        return False
    from .smtp_mail import recipients
    tos = recipients(to)
    if not tos:
        log.error("Cannot send email: no recipient (set BRIEF_RECIPIENT).")
        return False
    try:
        message = MIMEText(html_body, "html", "utf-8")
        message["to"] = ", ".join(tos)
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        log.info("Brief emailed to %s", ", ".join(tos))
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Email send failed: %s", exc)
        return False


def _sender_name(sender: str) -> str:
    if "<" in sender:
        return sender.split("<")[0].strip().strip('"') or sender
    return sender
