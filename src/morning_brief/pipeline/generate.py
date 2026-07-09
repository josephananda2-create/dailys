"""Assemble the brief: build LLM context, call the LLM, or fall back to a
deterministic extractive renderer (so a brief is ALWAYS produced).
"""
from __future__ import annotations

from ..config_loader import Config
from ..models import Item
from ..utils.dates import today_str
from ..utils.logging import get_logger
from . import summarize
from .score import group_by_section, top_n

log = get_logger()

SECTION_TITLES = {
    "advertising": "Advertising",
    "strategy": "Strategy",
    "world": "World",
    "malaysia": "Malaysia",
    "client_category": "Client category watch",
    "ai": "AI",
    "sports": "Sports",
    "day_ahead": "My day ahead",
}


def build_context(scored: list[Item], events: list[Item], cfg: Config, report: dict) -> dict:
    sections = group_by_section(scored, cfg)
    picks = top_n(scored, cfg)
    return {
        "date": today_str(),
        "top_picks": [p.id for p in picks],
        "sections": {sec: [i.to_context() for i in items] for sec, items in sections.items()},
        "calendar": [e.to_context() for e in events],
        "run_report": {
            "sources_ok": report.get("ok", []),
            "sources_failed": [f["name"] for f in report.get("failed", [])],
            "sources_paused": report.get("skipped", []),
        },
    }


def generate(scored: list[Item], events: list[Item], cfg: Config, report: dict) -> tuple[str, dict]:
    context = build_context(scored, events, cfg, report)
    markdown = summarize.render_with_llm(context)
    if not markdown:
        markdown = _render_fallback(scored, events, cfg, report)
    return markdown, context


# --- deterministic fallback (no LLM) -----------------------------------------
def _cite(item: Item) -> str:
    return f"[{item.source_name}, {item.date_str}]({item.url})"


def _item_line(item: Item) -> str:
    flag = " _(update)_" if item.is_update else ""
    wl = f" — _watchlist: {', '.join(str(h) for h in item.watchlist_hits)}_" if item.watchlist_hits else ""
    snippet = item.summary.strip()
    body = f" {snippet}" if snippet else ""
    return f"- **{item.title.strip()}**{flag} —{body} {_cite(item)}{wl}"


def _render_fallback(scored: list[Item], events: list[Item], cfg: Config, report: dict) -> str:
    date = today_str()
    sections = group_by_section(scored, cfg)
    picks = top_n(scored, cfg)
    out: list[str] = [f"# Morning Brief: {date}", ""]
    out.append("> ⚠️ Extractive mode (no LLM key set). Headlines and sources are real; "
               "no AI rewriting or synthesis. Set `ANTHROPIC_API_KEY` for the full brief.")
    out.append("")

    out.append("## 1. The 10 things you need to know today")
    if picks:
        out += [_item_line(p) for p in picks]
    else:
        out.append("- Nothing cleared the bar today.")
    out.append("")

    order = [
        ("advertising", "## 2. Advertising and strategy radar"),
        ("strategy", None),
        ("world", "## 3. World radar"),
        ("malaysia", "## 4. Malaysia radar"),
        ("client_category", "## 5. Client category watch"),
        ("ai", "## 6. AI watch"),
        ("sports", "## 7. Sports corner"),
    ]
    for sec, header in order:
        if header:
            out.append(header)
        items = sections.get(sec, [])
        if sec == "strategy":
            out.append("**Strategy thinking**")
        if items:
            out += [_item_line(i) for i in items]
        else:
            out.append("- Nothing that clears the bar today.")
        out.append("")

    out.append("## 8. My day ahead")
    if events:
        for e in events:
            loc = e.extra.get("location", "")
            loc = f" @ {loc}" if loc else ""
            out.append(f"- **{e.title}**{loc} {('— ' + e.summary) if e.summary else ''}")
    else:
        out.append("- No calendar connected, or nothing scheduled.")
    out.append("")

    out.append("## 9. Strategist's takeaway")
    out.append("- _(LLM disabled — takeaways are synthesised only when `ANTHROPIC_API_KEY` is set.)_")
    out.append("")

    out.append("## 10. Source list")
    seen = set()
    all_items = [i for lst in sections.values() for i in lst] + picks
    for i in all_items:
        key = i.url or i.title
        if key in seen:
            continue
        seen.add(key)
        out.append(f"- {_cite(i)}")
    out.append("")

    failed = report.get("failed", [])
    if failed:
        out.append("---")
        out.append(f"_Sources that failed this run: {', '.join(f['name'] for f in failed)}._")
    return "\n".join(out)
