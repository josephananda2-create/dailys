"""Notion connector: archive each daily brief as a nicely-formatted page.

Creates one child page per day under NOTION_PARENT_PAGE_ID, with a ☀️ icon, a
cover, a callout intro, section dividers, and proper rich text (bold, italic,
clickable links) parsed from the markdown — not raw `**` / `[]()`.

Cross-day de-duplication lives in the local seen-store, so no Notion database is
needed. `append_seen` is a no-op kept for compatibility.

Degrades gracefully: no key / page / client → returns None/False.
"""
from __future__ import annotations

import re

from ..config_loader import env
from ..utils.logging import get_logger

log = get_logger()

COVER_URL = "https://www.notion.so/images/page-cover/gradients_8.png"
_MAX_CHILDREN = 90  # Notion caps children per request at 100; stay safely under.


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
    client = _client()
    parent = env("NOTION_PARENT_PAGE_ID")
    if client is None or not parent:
        log.info("Notion not configured; skipping archive save.")
        return None
    try:
        blocks = _markdown_to_blocks(markdown)
        page = client.pages.create(
            parent={"type": "page_id", "page_id": parent},
            icon={"type": "emoji", "emoji": "☀️"},
            cover={"type": "external", "external": {"url": COVER_URL}},
            properties={"title": {"title": [{"text": {"content": title}}]}},
            children=blocks[:_MAX_CHILDREN],
        )
        # Append any remaining blocks in batches (long briefs exceed one request).
        page_id = page["id"]
        for i in range(_MAX_CHILDREN, len(blocks), _MAX_CHILDREN):
            client.blocks.children.append(block_id=page_id, children=blocks[i:i + _MAX_CHILDREN])
        url = page.get("url")
        log.info("Saved brief to Notion: %s", url)
        return url
    except Exception as exc:  # noqa: BLE001
        log.error("Notion save failed: %s", exc)
        return None


def append_seen(records: list[dict]) -> None:
    """No-op: dedup memory lives in the local seen-store. Kept for compatibility."""
    return None


# --- markdown → Notion blocks ------------------------------------------------
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?:\*([^*]+)\*|_([^_]+)_)")


def _markdown_to_blocks(md: str) -> list[dict]:
    blocks: list[dict] = []
    first_h2_seen = False
    for line in md.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue
        if raw.startswith("# "):
            blocks.append(_text_block("heading_1", raw[2:]))
        elif raw.startswith("## "):
            # Divider between top-level sections for visual separation.
            if first_h2_seen:
                blocks.append({"object": "block", "type": "divider", "divider": {}})
            first_h2_seen = True
            blocks.append(_text_block("heading_2", raw[3:]))
        elif raw.startswith("### "):
            blocks.append(_text_block("heading_3", raw[4:]))
        elif raw.startswith("> "):
            blocks.append({
                "object": "block", "type": "callout",
                "callout": {"rich_text": _rich_text(raw[2:]), "icon": {"type": "emoji", "emoji": "📌"}},
            })
        elif raw.lstrip().startswith(("- ", "* ")):
            blocks.append(_text_block("bulleted_list_item", raw.lstrip()[2:]))
        elif re.match(r"^\d+\.\s", raw.lstrip()):
            blocks.append(_text_block("numbered_list_item", re.sub(r"^\d+\.\s", "", raw.lstrip())))
        elif raw.startswith("---"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        else:
            blocks.append(_text_block("paragraph", raw))
    return blocks


def _text_block(kind: str, text: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": _rich_text(text)}}


def _rich_text(text: str) -> list[dict]:
    """Parse inline markdown (links, bold, italic) into Notion rich_text objects."""
    out: list[dict] = []
    pos = 0
    for m in _LINK.finditer(text):
        if m.start() > pos:
            out.extend(_styled(text[pos:m.start()]))
        out.append({
            "type": "text",
            "text": {"content": m.group(1)[:2000], "link": {"url": m.group(2)}},
        })
        pos = m.end()
    if pos < len(text):
        out.extend(_styled(text[pos:]))
    return out or [{"type": "text", "text": {"content": text[:2000]}}]


def _styled(text: str) -> list[dict]:
    """Apply bold, then italic, to a link-free text segment."""
    out: list[dict] = []
    last = 0
    for m in _BOLD.finditer(text):
        if m.start() > last:
            out.extend(_italicize(text[last:m.start()]))
        out.append({"type": "text", "text": {"content": m.group(1)[:2000]},
                    "annotations": {"bold": True}})
        last = m.end()
    if last < len(text):
        out.extend(_italicize(text[last:]))
    return out


def _italicize(text: str) -> list[dict]:
    out: list[dict] = []
    last = 0
    for m in _ITALIC.finditer(text):
        if m.start() > last:
            out.append({"type": "text", "text": {"content": text[last:m.start()][:2000]}})
        content = m.group(1) or m.group(2) or ""
        out.append({"type": "text", "text": {"content": content[:2000]},
                    "annotations": {"italic": True}})
        last = m.end()
    if last < len(text):
        out.append({"type": "text", "text": {"content": text[last:][:2000]}})
    return [o for o in out if o["text"]["content"]]
