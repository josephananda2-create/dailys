"""RSS / Atom connector. Zero credentials required.

Prefers `feedparser` (handles many feed quirks). Falls back to a small stdlib
parser (xml.etree) if feedparser isn't installed, so the core zero-credential
path works in any environment.
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET

from ..config_loader import Config
from ..models import Item, Source
from ..utils.dates import parse_dt
from ..utils.logging import get_logger
from ..utils.text import strip_html, truncate

log = get_logger()

_UA = "MorningBrief/0.1 (+https://github.com/) feed reader"

try:
    import feedparser  # type: ignore

    _HAVE_FEEDPARSER = True
except ImportError:  # pragma: no cover - env dependent
    _HAVE_FEEDPARSER = False


def fetch(source: Source, cfg: Config, limit: int = 25) -> list[Item]:
    url = source.url
    if not url or url.startswith("ADD_"):
        log.warning("RSS '%s': no usable URL, skipping.", source.name)
        return []

    section = cfg.section_for(source.category)
    raw_entries = _fetch_feedparser(url, limit) if _HAVE_FEEDPARSER else _fetch_stdlib(url, limit)

    items: list[Item] = []
    for e in raw_entries:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if not title or not link:
            continue
        items.append(
            Item(
                title=title,
                url=link,
                source_name=source.name,
                category=source.category,
                published=parse_dt(e.get("published")),
                summary=truncate(strip_html(e.get("summary") or ""), 600),
                section=section,
                region=source.region,
                tags=source.tags,
                reliability=source.reliability,
                priority=source.priority,
                kind="news",
            )
        )
    log.info("RSS '%s': %d items", source.name, len(items))
    return items


def _fetch_feedparser(url: str, limit: int) -> list[dict]:
    parsed = feedparser.parse(url, agent=_UA)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"feed parse failed: {getattr(parsed, 'bozo_exception', 'unknown')}")
    out = []
    for entry in parsed.entries[:limit]:
        out.append({
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published") or entry.get("updated") or entry.get("created"),
            "summary": entry.get("summary") or entry.get("description") or "",
        })
    return out


def _fetch_stdlib(url: str, limit: int) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - configured feeds only
        data = resp.read()
    root = ET.fromstring(data)

    def tag(el):  # strip namespace
        return el.tag.split("}")[-1]

    def text(el, *names):
        for name in names:
            child = el.find(name)
            if child is not None and child.text:
                return child.text
            # namespaced search
            for c in el:
                if tag(c) == name and c.text:
                    return c.text
        return ""

    entries = []
    nodes = [el for el in root.iter() if tag(el) in ("item", "entry")]
    for node in nodes[:limit]:
        link = text(node, "link")
        if not link:  # Atom <link href="">
            for c in node:
                if tag(c) == "link" and c.attrib.get("href"):
                    link = c.attrib["href"]
                    break
        entries.append({
            "title": text(node, "title"),
            "link": link,
            "published": text(node, "pubDate", "published", "updated"),
            "summary": text(node, "description", "summary", "content"),
        })
    return entries
