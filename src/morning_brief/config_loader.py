"""Load & validate config/*.yaml. Fail loud on malformed YAML, warn on soft issues."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Source
from .utils.logging import get_logger

log = get_logger()

VALID_TYPES = {
    "rss", "website", "newsletter", "api", "gmail_search",
    "manual", "youtube", "podcast", "social",
}
PLACEHOLDER = "ADD_"


@dataclass
class Config:
    sources: list[Source]
    categories: dict[str, Any]
    watchlist: list[dict]
    scoring: dict[str, Any]
    root: Path

    def section_for(self, category: str) -> str:
        cat = self.categories.get(category, {})
        return cat.get("section", "world") if isinstance(cat, dict) else "world"

    def keywords_for(self, category: str) -> list[str]:
        cat = self.categories.get(category, {})
        return cat.get("keywords", []) if isinstance(cat, dict) else []


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a YAML mapping at the top level.")
    return data


def load_config(root: str | Path = ".") -> Config:
    root = Path(root)
    cfg_dir = root / "config"
    src_raw = _read_yaml(cfg_dir / "sources.yaml")
    cats = _read_yaml(cfg_dir / "categories.yaml")
    scoring = _read_yaml(cfg_dir / "scoring.yaml")

    sources = []
    for i, s in enumerate(src_raw.get("sources", [])):
        if not isinstance(s, dict) or not s.get("name"):
            log.warning("Skipping malformed source at index %d", i)
            continue
        sources.append(
            Source(
                name=s["name"],
                type=str(s.get("type", "rss")).lower(),
                category=str(s.get("category", "world")),
                region=str(s.get("region", "global")),
                url=str(s.get("url", "")),
                query=str(s.get("query", "")),
                priority=int(s.get("priority", 5)),
                reliability=int(s.get("reliability", 5)),
                frequency=str(s.get("frequency", "daily")),
                active=bool(s.get("active", True)),
                tags=[str(t) for t in (s.get("tags", []) or [])],
                notes=str(s.get("notes", "")),
            )
        )

    return Config(
        sources=sources,
        categories=cats.get("categories", {}),
        watchlist=cats.get("watchlist", []),
        scoring=scoring,
        root=root,
    )


def validate_sources(root: str | Path = ".") -> ValidationResult:
    """Structural validation of sources.yaml (+ cross-checks vs categories)."""
    result = ValidationResult()
    root = Path(root)
    try:
        raw = _read_yaml(root / "config" / "sources.yaml")
        cats = _read_yaml(root / "config" / "categories.yaml").get("categories", {})
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        result.errors.append(str(exc))
        return result

    items = raw.get("sources")
    if not isinstance(items, list) or not items:
        result.errors.append("`sources:` must be a non-empty list.")
        return result

    seen_names: set[str] = set()
    for i, s in enumerate(items):
        where = f"source #{i + 1}"
        if not isinstance(s, dict):
            result.errors.append(f"{where}: must be a mapping.")
            continue
        name = s.get("name")
        if not name:
            result.errors.append(f"{where}: missing `name`.")
            name = where
        if name in seen_names:
            result.errors.append(f"{where}: duplicate name '{name}'.")
        seen_names.add(name)

        stype = str(s.get("type", "")).lower()
        if stype not in VALID_TYPES:
            result.errors.append(f"{name}: invalid type '{stype}'. Allowed: {sorted(VALID_TYPES)}")

        cat = s.get("category")
        if cat and cats and cat not in cats:
            result.warnings.append(f"{name}: category '{cat}' not defined in categories.yaml.")

        needs_query = stype in {"gmail_search", "api"}
        loc = s.get("query") if needs_query else s.get("url")
        if not loc:
            field_name = "query" if needs_query else "url"
            result.warnings.append(f"{name}: missing `{field_name}` — will be skipped at run time.")
        elif isinstance(loc, str) and loc.startswith(PLACEHOLDER):
            result.warnings.append(f"{name}: placeholder URL/query not filled in — will be skipped.")

        for num_field in ("priority", "reliability"):
            v = s.get(num_field, 5)
            if not isinstance(v, int) or not (1 <= v <= 10):
                result.warnings.append(f"{name}: {num_field}={v} should be an integer 1-10.")

        if "active" in s and not isinstance(s["active"], bool):
            result.warnings.append(f"{name}: `active` should be true/false.")

    return result


def env(key: str, default: str | None = None) -> str | None:
    val = os.getenv(key, default)
    return val.strip() if isinstance(val, str) else val
