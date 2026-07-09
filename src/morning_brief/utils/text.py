"""Text helpers: HTML stripping, normalization, similarity."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "as", "at",
    "by", "with", "from", "is", "are", "be", "this", "that", "it", "its",
}


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    if BeautifulSoup is not None:
        try:
            return _WS.sub(" ", BeautifulSoup(html, "html.parser").get_text(" ")).strip()
        except Exception:
            pass
    return _WS.sub(" ", re.sub(r"<[^>]+>", " ", html)).strip()


def truncate(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_title(title: str | None) -> str:
    t = (title or "").lower()
    t = _NONWORD.sub(" ", t)
    tokens = [w for w in t.split() if w not in _STOP]
    return " ".join(tokens)


def similarity(a: str, b: str) -> float:
    """0..1 fuzzy similarity of two normalized strings."""
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def contains_any(text: str, needles) -> list[str]:
    """Return the subset of `needles` (case-insensitive, word-ish) found in text."""
    low = (text or "").lower()
    hits = []
    for n in needles:
        n2 = str(n).lower().strip()
        if n2 and n2 in low:
            hits.append(n)
    return hits
