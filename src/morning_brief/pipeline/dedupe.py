"""De-duplication.

Two passes:
  1. Within this run: cluster near-identical titles, keep the most reliable/fresh
     representative, and record corroboration (how many sources carried it).
  2. Across days: drop stories already included in the last N days (seen store),
     unless content changed enough to count as a "meaningful update".
"""
from __future__ import annotations

from ..config_loader import Config
from ..models import Item
from ..utils.logging import get_logger
from ..utils.text import normalize_title, similarity
from .seen_store import SeenStore

log = get_logger()


def _rep_sort_key(item: Item):
    # Prefer higher reliability, then higher priority, then fresher.
    ts = item.published.timestamp() if item.published else 0
    return (item.reliability, item.priority, ts)


def dedupe_within_run(items: list[Item], cfg: Config) -> list[Item]:
    threshold = cfg.scoring.get("dedupe", {}).get("title_similarity", 0.72)
    clusters: list[list[Item]] = []

    for item in items:
        placed = False
        norm = normalize_title(item.title)
        for cluster in clusters:
            if similarity(norm, cluster[0].title) >= threshold:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    reps: list[Item] = []
    for cluster in clusters:
        cluster.sort(key=_rep_sort_key, reverse=True)
        rep = cluster[0]
        others = {i.source_name for i in cluster[1:]}
        rep.corroborated_by = sorted(others)
        reps.append(rep)

    log.info("Dedupe (within run): %d → %d items.", len(items), len(reps))
    return reps


def filter_seen(items: list[Item], cfg: Config, store: SeenStore) -> list[Item]:
    dd = cfg.scoring.get("dedupe", {})
    update_delta = dd.get("meaningful_update_delta", 0.35)
    kept: list[Item] = []
    dropped = 0
    for item in items:
        prev = store.find(item.title)
        if prev is None:
            kept.append(item)
            continue
        # Seen before — only keep if content changed meaningfully.
        change = 1.0 - similarity(item.summary or item.title, prev.get("summary") or prev.get("title", ""))
        if change >= update_delta:
            item.is_update = True
            kept.append(item)
        else:
            dropped += 1
    log.info("Dedupe (across days): dropped %d already-seen, kept %d.", dropped, len(kept))
    return kept
