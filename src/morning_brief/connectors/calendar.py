"""Google Calendar connector: today's & tomorrow's events → Items + topic tags."""
from __future__ import annotations

from datetime import timedelta

from ..config_loader import Config
from ..models import Item
from ..utils.dates import now_local, parse_dt, tz
from ..utils.logging import get_logger
from ..utils.text import truncate
from .google_auth import build_service

log = get_logger()


def available() -> bool:
    return build_service("calendar", "v3") is not None


def fetch(cfg: Config, days_ahead: int = 2) -> list[Item]:
    """Return calendar events from now through `days_ahead` days as Items."""
    service = build_service("calendar", "v3")
    if service is None:
        log.info("Calendar unavailable; skipping.")
        return []

    start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days_ahead)
    items: list[Item] = []
    try:
        events = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
        )
        for ev in events.get("items", []):
            summary = ev.get("summary", "(untitled event)")
            start_raw = ev.get("start", {})
            when = start_raw.get("dateTime") or start_raw.get("date")
            published = parse_dt(when)
            day_label = _day_label(published)
            desc = ev.get("description", "") or ""
            attendees = [a.get("email", "") for a in ev.get("attendees", [])]
            items.append(
                Item(
                    title=f"[{day_label}] {summary}",
                    url=ev.get("htmlLink", ""),
                    source_name="Google Calendar",
                    category="day_ahead",
                    published=published,
                    summary=truncate(desc, 300),
                    section="day_ahead",
                    region="personal",
                    tags=_event_tags(summary + " " + desc),
                    reliability=10,
                    priority=10,
                    kind="event",
                    extra={"attendees": attendees, "location": ev.get("location", ""), "day": day_label},
                )
            )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"calendar fetch failed: {exc}") from exc

    log.info("Calendar: %d events", len(items))
    return items


def meeting_keywords(events: list[Item]) -> set[str]:
    """Words from meeting titles/descriptions used to boost same-topic news today."""
    words: set[str] = set()
    for ev in events:
        for w in (ev.title + " " + ev.summary).lower().split():
            w = w.strip(".,:;!?\"'()[]")
            if len(w) > 4:
                words.add(w)
    return words


def _day_label(dt) -> str:
    if dt is None:
        return "soon"
    local = dt.astimezone(tz())
    today = now_local().date()
    delta = (local.date() - today).days
    return {0: "today", 1: "tomorrow"}.get(delta, local.strftime("%a %d %b"))


def _event_tags(text: str) -> list[str]:
    low = text.lower()
    tags = []
    for kw in ("pitch", "client", "deadline", "review", "workshop", "presentation", "deck", "brief"):
        if kw in low:
            tags.append(kw)
    return tags
