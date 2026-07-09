"""Notion connector: archive the daily brief + persist the seen-story log.

Auto-provisions two databases under NOTION_PARENT_PAGE_ID on first use:
  - "Morning Brief Archive"  (one page per day, full markdown body)
  - "Seen Stories Log"       (dedupe memory across days)

Degrades gracefully: if NOTION_API_KEY / parent page are missing or the client
isn't installed, every function no-ops and returns False/empty.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config_loader import env
from ..utils.logging import get_logger

log = get_logger()

_STATE = Path("data/state/notion_dbs.json")
ARCHIVE_DB = "Morning Brief Archive"
SEEN_DB = "Seen Stories Log"


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


# --- database bootstrap ------------------------------------------------------
def _load_db_ids() -> dict:
    if _STATE.exists():
        try:
            return json.loads(_STATE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_db_ids(ids: dict) -> None:
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(ids, indent=2))


def _ensure_databases(client) -> dict:
    ids = _load_db_ids()
    if ids.get(ARCHIVE_DB) and ids.get(SEEN_DB):
        return ids
    parent_page = env("NOTION_PARENT_PAGE_ID")
    if not parent_page:
        return ids

    if not ids.get(ARCHIVE_DB):
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_page},
            title=[{"type": "text", "text": {"content": ARCHIVE_DB}}],
            properties={
                "Name": {"title": {}},
                "Date": {"date": {}},
                "Sections": {"number": {}},
                "Items": {"number": {}},
            },
        )
        ids[ARCHIVE_DB] = db["id"]
        log.info("Created Notion database '%s'", ARCHIVE_DB)

    if not ids.get(SEEN_DB):
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_page},
            title=[{"type": "text", "text": {"content": SEEN_DB}}],
            properties={
                "Title": {"title": {}},
                "URL": {"url": {}},
                "Date": {"date": {}},
                "Category": {"rich_text": {}},
            },
        )
        ids[SEEN_DB] = db["id"]
        log.info("Created Notion database '%s'", SEEN_DB)

    _save_db_ids(ids)
    return ids


# --- public API --------------------------------------------------------------
def save_brief(title: str, date_iso: str, markdown: str, n_sections: int, n_items: int) -> str | None:
    """Create one archive page for today's brief. Returns the page URL or None."""
    client = _client()
    if client is None or not env("NOTION_PARENT_PAGE_ID"):
        log.info("Notion not configured; skipping archive save.")
        return None
    try:
        ids = _ensure_databases(client)
        page = client.pages.create(
            parent={"database_id": ids[ARCHIVE_DB]},
            properties={
                "Name": {"title": [{"text": {"content": title}}]},
                "Date": {"date": {"start": date_iso}},
                "Sections": {"number": n_sections},
                "Items": {"number": n_items},
            },
            children=_markdown_to_blocks(markdown),
        )
        url = page.get("url")
        log.info("Saved brief to Notion: %s", url)
        return url
    except Exception as exc:  # noqa: BLE001
        log.error("Notion save failed: %s", exc)
        return None


def append_seen(records: list[dict]) -> None:
    """Persist today's included stories to the Seen Stories Log (best-effort)."""
    client = _client()
    if client is None or not env("NOTION_PARENT_PAGE_ID") or not records:
        return
    try:
        ids = _ensure_databases(client)
        db_id = ids.get(SEEN_DB)
        for r in records[:100]:
            client.pages.create(
                parent={"database_id": db_id},
                properties={
                    "Title": {"title": [{"text": {"content": r.get("title", "")[:200]}}]},
                    "URL": {"url": r.get("url") or None},
                    "Date": {"date": {"start": r.get("date")}} if r.get("date") else {"date": None},
                    "Category": {"rich_text": [{"text": {"content": r.get("category", "")}}]},
                },
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Notion seen-log append failed: %s", exc)


def _markdown_to_blocks(md: str) -> list[dict]:
    """Very small Markdown → Notion blocks converter (headings, bullets, text)."""
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
