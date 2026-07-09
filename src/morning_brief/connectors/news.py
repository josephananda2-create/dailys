"""Optional NewsAPI connector for `type: api` sources (https://newsapi.org).

Skipped silently if NEWSAPI_KEY is not set. The `query` field of the source is
used as the NewsAPI `q` parameter.
"""
from __future__ import annotations

import requests

from ..config_loader import Config, env
from ..models import Item, Source
from ..utils.dates import parse_dt
from ..utils.logging import get_logger
from ..utils.text import truncate

log = get_logger()

_ENDPOINT = "https://newsapi.org/v2/everything"


def fetch(source: Source, cfg: Config, limit: int = 15) -> list[Item]:
    key = env("NEWSAPI_KEY")
    if not key:
        log.info("NewsAPI not configured; skipping '%s'.", source.name)
        return []
    query = source.query or source.url
    if not query:
        return []

    section = cfg.section_for(source.category)
    params = {
        "q": query,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": limit,
        "apiKey": key,
    }
    resp = requests.get(_ENDPOINT, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {data.get('message')}")

    items: list[Item] = []
    for art in data.get("articles", []):
        title = art.get("title")
        url = art.get("url")
        if not title or not url:
            continue
        items.append(
            Item(
                title=title,
                url=url,
                source_name=f"{art.get('source', {}).get('name', source.name)}",
                category=source.category,
                published=parse_dt(art.get("publishedAt")),
                summary=truncate(art.get("description") or "", 500),
                section=section,
                region=source.region,
                tags=source.tags,
                reliability=source.reliability,
                priority=source.priority,
                kind="news",
            )
        )
    log.info("NewsAPI '%s': %d items", source.name, len(items))
    return items
