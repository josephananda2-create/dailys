"""Collection: run every active source through its connector.

A single source failing is logged and skipped — it never stops the run.
Returns (items, calendar_events, run_report).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config_loader import Config
from ..connectors import calendar as calendar_conn
from ..connectors import gmail, news, rss
from ..models import Item, Source
from ..utils.logging import get_logger

log = get_logger()


def _fetch_one(source: Source, cfg: Config) -> list[Item]:
    if source.type in ("rss", "website", "newsletter", "youtube", "podcast", "social"):
        # website/newsletter/etc. are treated as feeds; if a page isn't a feed
        # it simply yields nothing and is skipped.
        return rss.fetch(source, cfg)
    if source.type == "gmail_search":
        return gmail.fetch(source, cfg)
    if source.type == "api":
        return news.fetch(source, cfg)
    if source.type == "manual":
        # Manual links: surface the single URL as an item.
        if source.url and not source.url.startswith("ADD_"):
            return [
                Item(
                    title=source.name,
                    url=source.url,
                    source_name=source.name,
                    category=source.category,
                    section=cfg.section_for(source.category),
                    region=source.region,
                    tags=source.tags,
                    reliability=source.reliability,
                    priority=source.priority,
                    summary=source.notes,
                )
            ]
        return []
    log.warning("Unknown source type '%s' for '%s'.", source.type, source.name)
    return []


def collect(cfg: Config, max_workers: int = 8) -> tuple[list[Item], list[Item], dict]:
    active = [s for s in cfg.sources if s.active]
    skipped = [s for s in cfg.sources if not s.active]
    report = {"ok": [], "failed": [], "skipped": [s.name for s in skipped], "counts": {}}

    log.info("Collecting from %d active sources (%d paused)…", len(active), len(skipped))
    items: list[Item] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, s, cfg): s for s in active}
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                got = fut.result()
                items.extend(got)
                report["ok"].append(src.name)
                report["counts"][src.name] = len(got)
            except Exception as exc:  # noqa: BLE001 - never let one source kill the run
                log.error("Source '%s' failed: %s", src.name, exc)
                report["failed"].append({"name": src.name, "error": str(exc)})

    # Calendar is fetched once (not per-source).
    events: list[Item] = []
    try:
        events = calendar_conn.fetch(cfg)
        report["ok"].append("Google Calendar")
        report["counts"]["Google Calendar"] = len(events)
    except Exception as exc:  # noqa: BLE001
        log.error("Calendar failed: %s", exc)
        report["failed"].append({"name": "Google Calendar", "error": str(exc)})

    log.info("Collected %d news/email items + %d events.", len(items), len(events))
    return items, events, report
