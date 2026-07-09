"""Local seen-story memory (data/seen_stories.json).

Keeps the running log of what was included, so the same story does not repeat
across days unless there is a meaningful update. Notion holds the durable copy;
this local file is the fast path the pipeline reads/writes each run.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..utils.logging import get_logger
from ..utils.text import normalize_title, similarity

log = get_logger()


class SeenStore:
    def __init__(self, path: str | Path = "data/seen_stories.json", window_days: int = 5,
                 similarity_threshold: float = 0.72):
        self.path = Path(path)
        self.window_days = window_days
        self.threshold = similarity_threshold
        self.records: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        fresh = []
        for r in data:
            try:
                seen_at = datetime.fromisoformat(r.get("seen_at", ""))
            except ValueError:
                continue
            if seen_at.tzinfo is None:
                seen_at = seen_at.replace(tzinfo=timezone.utc)
            if seen_at >= cutoff:
                fresh.append(r)
        return fresh

    def find(self, title: str) -> dict | None:
        norm = normalize_title(title)
        for r in self.records:
            if similarity(norm, r.get("norm_title", r.get("title", ""))) >= self.threshold:
                return r
        return None

    def add_many(self, items) -> list[dict]:
        added = []
        now = datetime.now(timezone.utc).isoformat()
        for it in items:
            rec = {
                "title": it.title,
                "norm_title": normalize_title(it.title),
                "url": it.url,
                "summary": it.summary[:300],
                "category": it.category,
                "date": it.date_str,
                "seen_at": now,
            }
            self.records.append(rec)
            added.append(rec)
        return added

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.records, indent=2, ensure_ascii=False))
        except OSError as exc:
            log.warning("Could not persist seen store: %s", exc)
