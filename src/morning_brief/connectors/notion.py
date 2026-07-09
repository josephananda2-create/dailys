"""Notion connector: archive each daily brief as a page under a parent page.

Design: we create one child page per day directly under NOTION_PARENT_PAGE_ID,
titled "Morning Brief — <date>", with the brief markdown as the page body. This
avoids the database/data-source schema complexities of the newer Notion API and
"just works" as long as the parent page is shared with the integration.

Cross-day de-duplication is handled by the local seen-story log
(data/seen_stories.json, persisted between runs), so we do not need a Notion
database for it. `append_seen` is kept as a no-op for backwards compatibility.

Degrades gracefully: if NOTION_API_KEY / parent page are missing or the client
isn't installed, every function no-ops and returns None/False.
"""
from __future__ import annotations

from ..config_loader import env
from ..utils.logging import get_logger

log = get_logger()


def _client():
    key = env("NOTION_API_KEY")
    if not key:
        return None
    try:
        from notion_client import Client
    except ImportError:
        log.warning("notion-client not installed; run `pip install .[notion]`.")
        return None
    return Client(auth=key)


def available() -> bool:
    return _client() is not None and bool(env("NOTION_PARENT_PAGE_ID"))


def save_brief(title: str, date_iso: str, markdown: str,
               n_sections: int = 0, n_items: int = 0) -> str | None:
    """Create one archive page for today's brief. Returns the page URL or None."""
    client = _client()
    parent = env("NOTION_PARENT_PAGE_ID")
    if client is None or not parent:
        log.info("Notion not configured; skipping archive save.")
        return None
    try:
        page = client.pages.create(
            parent={"type": "page_id", "page_id": parent},
            properties={"title": {"title": [{"text": {"content": title}}]}},
            children=_markdown_to_blocks(markdown),
        )
        url = page.get("url")
        log.info("Saved brief to Notion: %s", url)
        return url
    except Exception as exc:  # noqa: BLE001
        log.error("Notion save failed: %s", exc)
        return None


def append_seen(records: list[dict]) -> None:
    """No-op: dedup memory lives in the local seen-story log. Kept for compatibility."""
    return None


# --- markdown → Notion blocks ------------------------------------------------
def _markdown_to_blocks(md: str) -> list[dict]:
    """Small Markdown → Notion blocks converter (headings, bullets, text)."""
    blocks: list[dict] = []
    for line in md.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue
        if raw.startswith("### "):
            blocks.append(_block("heading_3", raw[4:]))
        elif raw.startswith("## "):
            blocks.append(_block("heading_2", raw[3:]))
        elif raw.startswith("# "):
            blocks.append(_block("heading_1", raw[2:]))
        elif raw.lstrip().startswith(("- ", "* ")):
            blocks.append(_block("bulleted_list_item", raw.lstrip()[2:]))
        elif raw.startswith("> "):
            blocks.append(_block("quote", raw[2:]))
        else:
            blocks.append(_block("paragraph", raw))
        if len(blocks) >= 95:  # Notion caps children per request
            break
    return blocks


def _block(kind: str, text: str) -> dict:
    return {
        "object": "block",
        "type": kind,
        kind: {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]},
    }
