"""Relevance scoring + ranking.

Score = weighted sum of: source priority, source reliability, freshness,
category-keyword match, client watchlist match, calendar-topic match,
inbox-topic corroboration, and multi-source corroboration.

Guardrail: items from low-reliability sources are dropped unless corroborated.
"""
from __future__ import annotations

import math

from ..config_loader import Config
from ..models import Item
from ..utils.dates import age_hours
from ..utils.logging import get_logger
from ..utils.text import contains_any

log = get_logger()


def _freshness(item: Item, half_life: float) -> float:
    hrs = age_hours(item.published)
    if hrs is None:
        return 0.3  # unknown date — mild penalty, not zero
    return math.pow(0.5, hrs / max(half_life, 1e-6))


def _flatten_watchlist(cfg: Config) -> list[tuple[str, str]]:
    pairs = []
    for w in cfg.watchlist:
        client = w.get("client", "")
        for b in (w.get("brands", []) + w.get("competitors", [])):
            pairs.append((b, client))
    return pairs


def score_items(
    items: list[Item],
    cfg: Config,
    calendar_words: set[str] | None = None,
    inbox_topics: set[str] | None = None,
) -> list[Item]:
    w = cfg.scoring.get("weights", {})
    half_life = cfg.scoring.get("freshness_half_life_hours", 24)
    max_age = cfg.scoring.get("max_age_hours", 72)
    low_rel = cfg.scoring.get("low_reliability_threshold", 6)
    calendar_words = calendar_words or set()
    inbox_topics = inbox_topics or set()
    watchlist = _flatten_watchlist(cfg)

    # Age filter first.
    kept = []
    for it in items:
        hrs = age_hours(it.published)
        if hrs is not None and hrs > max_age:
            continue
        kept.append(it)

    for it in kept:
        text = f"{it.title} {it.summary}"
        bd: dict[str, float] = {}

        bd["priority"] = it.priority * w.get("priority", 1.6)
        bd["reliability"] = it.reliability * w.get("reliability", 0.8)
        bd["freshness"] = _freshness(it, half_life) * w.get("freshness", 3.0)

        cat_kw = cfg.keywords_for(it.category)
        if contains_any(text, cat_kw):
            bd["category_match"] = w.get("category_match", 2.0)

        hits = contains_any(text, [b for b, _ in watchlist])
        if hits:
            it.watchlist_hits = hits
            bd["watchlist_match"] = w.get("watchlist_match", 4.0) * min(len(hits), 2)

        if calendar_words:
            words = set(text.lower().replace(",", " ").split())
            if words & calendar_words or set(t.lower() for t in it.tags) & calendar_words:
                bd["calendar_match"] = w.get("calendar_match", 3.0)

        if inbox_topics:
            words = set(text.lower().split())
            if words & inbox_topics:
                bd["gmail_topic_match"] = w.get("gmail_topic_match", 1.5)

        if it.corroborated_by:
            bd["corroboration"] = w.get("corroboration", 2.0) * min(len(it.corroborated_by), 3)

        it.score_breakdown = bd
        it.score = round(sum(bd.values()), 3)

    # Low-reliability guardrail: require corroboration to survive.
    survivors = []
    for it in kept:
        if it.reliability < low_rel and not it.corroborated_by and not it.watchlist_hits:
            log.debug("Dropping low-reliability uncorroborated item: %s", it.title[:60])
            continue
        survivors.append(it)

    survivors.sort(key=lambda x: x.score, reverse=True)
    log.info("Scored %d items (%d after age/reliability filters).", len(items), len(survivors))
    return survivors


def group_by_section(items: list[Item], cfg: Config) -> dict[str, list[Item]]:
    caps = cfg.scoring.get("section_caps", {})
    sections: dict[str, list[Item]] = {}
    for it in items:
        sections.setdefault(it.section, []).append(it)
    for sec, lst in sections.items():
        lst.sort(key=lambda x: x.score, reverse=True)
        cap = caps.get(sec, 8)
        sections[sec] = lst[:cap]
    return sections


def top_n(items: list[Item], cfg: Config) -> list[Item]:
    n = cfg.scoring.get("top_n", 10)
    # Exclude personal calendar events from the global "need to know" list.
    ranked = [i for i in items if i.section != "day_ahead"]
    return ranked[:n]
