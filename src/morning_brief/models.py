"""Core data structures passed through the pipeline."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Source:
    name: str
    type: str
    category: str
    region: str = "global"
    url: str = ""
    query: str = ""
    priority: int = 5
    reliability: int = 5
    frequency: str = "daily"
    active: bool = True
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def location(self) -> str:
        """Where to fetch from — url for feeds, query for searches."""
        return self.query or self.url


@dataclass
class Item:
    """A single collected story/email/event."""
    title: str
    url: str
    source_name: str
    category: str
    published: datetime | None = None
    summary: str = ""            # raw snippet from the source (not LLM)
    section: str = "world"       # resolved from categories.yaml
    region: str = "global"
    tags: list[str] = field(default_factory=list)
    reliability: int = 5
    priority: int = 5
    kind: str = "news"           # news | email | event
    extra: dict[str, Any] = field(default_factory=dict)

    # Filled by the pipeline:
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    corroborated_by: list[str] = field(default_factory=list)
    watchlist_hits: list[str] = field(default_factory=list)
    is_update: bool = False

    @property
    def id(self) -> str:
        basis = (self.url or "") + "|" + (self.title or "")
        return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:16]

    @property
    def date_str(self) -> str:
        return self.published.strftime("%Y-%m-%d") if self.published else "n.d."

    def to_context(self) -> dict:
        """Compact dict handed to the LLM. Only real, fetched facts."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source_name,
            "url": self.url,
            "date": self.date_str,
            "category": self.category,
            "section": self.section,
            "region": self.region,
            "snippet": self.summary[:600],
            "kind": self.kind,
            "watchlist": self.watchlist_hits,
            "corroborated_by": self.corroborated_by,
            "is_update": self.is_update,
        }
