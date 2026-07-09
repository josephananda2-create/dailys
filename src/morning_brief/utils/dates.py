"""Date/time helpers. All 'today' logic is anchored to Asia/Kuala_Lumpur."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dateutil import parser as dateparser

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9
    ZoneInfo = None  # type: ignore

DEFAULT_TZ = os.getenv("TZ", "Asia/Kuala_Lumpur")


def tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(DEFAULT_TZ)
        except Exception:
            pass
    return timezone.utc


def now_local() -> datetime:
    return datetime.now(tz())


def today_str() -> str:
    """Human date for the brief header, e.g. 'Thursday, 9 July 2026'."""
    return now_local().strftime("%A, %-d %B %Y")


def today_iso() -> str:
    return now_local().date().isoformat()


def parse_dt(value) -> datetime | None:
    """Parse many date formats to an aware UTC datetime. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = dateparser.parse(str(value))
        except (ValueError, OverflowError, TypeError):
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def age_hours(dt: datetime | None, ref: datetime | None = None) -> float | None:
    if dt is None:
        return None
    ref = ref or datetime.now(timezone.utc)
    return max(0.0, (ref - dt).total_seconds() / 3600.0)
