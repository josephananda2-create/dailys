"""Weekly wrap-up: synthesise the past week's daily briefs into one email.

Reads the daily markdown archives from data/archive/brief-YYYY-MM-DD.md and
asks the LLM for a cross-week synthesis (themes, biggest stories, strategy
takeaways) — not a day-by-day recap. Falls back to a deterministic stitched
digest of each day's top-10 list when no LLM is configured.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from ..config_loader import env
from ..utils.dates import now_local
from ..utils.logging import get_logger

log = get_logger()

ARCHIVE_DIR = Path("data/archive")
_BRIEF_RE = re.compile(r"^brief-(\d{4}-\d{2}-\d{2})\.md$")

WEEKLY_SYSTEM_PROMPT = """\
You are the editor of a weekly wrap-up for a senior advertising strategist in \
Malaysia. Your reader is smart and time-poor. Write sharp, plain, useful \
English a 10-year-old could follow but a senior strategist still respects.

ABSOLUTE RULES:
- Use ONLY the daily briefs provided in the input JSON. Never invent facts, \
numbers, quotes, or events. If something is not in the briefs, do not say it.
- Carry citations through: every factual claim keeps its \
[Source name, YYYY-MM-DD](url) link from the daily brief it came from.
- SYNTHESISE across the week — pick out the stories that grew, connected, or \
mattered most. Do NOT recap day by day.
- Deduplicate: a story covered on several days appears ONCE, with how it developed.
- Be blunt when something is overhyped or strategically weak. No fluff, no hype.
- Some days may be missing from the input; work with what is provided and \
never mention gaps, feeds, or any system/plumbing detail.

Return GitHub-flavoured Markdown ONLY, following the exact section structure \
requested. Do not add a preamble or sign-off.
"""

WEEKLY_USER_TEMPLATE = """\
Week ending: {date}

Here are this week's daily briefs as JSON (oldest first).
```json
{payload}
```

Produce the weekly wrap-up with EXACTLY these sections and headings:

# Weekly Brief — week ending {date}

## 1. The 5 biggest things this week
The five stories that mattered most across the whole week. Each: **Headline** — \
what happened and how it developed over the week (2-3 plain sentences) — why it \
matters (1-2 concrete sentences) — source link(s).

## 2. Themes and throughlines
2-4 patterns that connect multiple stories from different days — the "what's \
really going on" layer. Each: the theme / the evidence (with citations) / what it \
signals for brands and communication.

## 3. Malaysia this week
The week's most useful Malaysia developments for Malaysian brand strategy.

## 4. Strategy takeaways for next week
3-5 sharp, marketing/communications-STRATEGY observations drawn from the week. \
Each: what it means / how to use it (brief, deck, pitch, client convo) / which \
client or category it applies to.

## 5. One thing to try
ONE practical thing (tool, technique, angle) from the week worth trying next week.

## 6. Source list
Bullet every source cited above, as [Name, date](url).
"""


def load_archives(days: int = 7, archive_dir: str | Path = ARCHIVE_DIR) -> list[tuple[str, str]]:
    """Return [(iso_date, markdown), ...] for daily briefs from the last `days` days,
    oldest first. Weekly outputs (weekly-*.md) are never picked up."""
    d = Path(archive_dir)
    if not d.exists():
        return []
    cutoff = now_local().date() - timedelta(days=days - 1)
    briefs: list[tuple[str, str]] = []
    for path in sorted(d.iterdir()):
        m = _BRIEF_RE.match(path.name)
        if not m:
            continue
        try:
            day = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if day < cutoff:
            continue
        briefs.append((m.group(1), path.read_text(encoding="utf-8")))
    return briefs


def render_weekly(briefs: list[tuple[str, str]], week_ending: str) -> str | None:
    """LLM synthesis of the week. Returns None if the LLM isn't configured/available."""
    api_key = env("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("ANTHROPIC_API_KEY not set — using stitched fallback for the weekly brief.")
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic not installed; run `pip install .[llm]`.")
        return None

    model = env("BRIEF_MODEL") or "claude-sonnet-5"
    # Keep payload bounded to control cost/latency: drop oldest days first.
    docs = [{"date": d, "markdown": md} for d, md in briefs]
    payload = json.dumps(docs, ensure_ascii=False, indent=1)
    while len(payload) > 150_000 and len(docs) > 1:
        docs.pop(0)
        payload = json.dumps(docs, ensure_ascii=False, indent=1)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=model,
            max_tokens=64000,
            system=WEEKLY_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": WEEKLY_USER_TEMPLATE.format(date=week_ending, payload=payload),
            }],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(block.text for block in msg.content if block.type == "text")
        if not text.strip():
            log.error("LLM returned empty text (stop_reason=%s); falling back.", msg.stop_reason)
            return None
        log.info("Weekly brief generated with %s (%d chars).", model, len(text))
        return text.strip()
    except Exception as exc:  # noqa: BLE001
        log.error("Weekly LLM generation failed (%s); falling back.", exc)
        return None


def render_weekly_fallback(briefs: list[tuple[str, str]], week_ending: str) -> str:
    """Deterministic digest: stitch each day's top-10 list under a per-day header."""
    out = [f"# Weekly Brief — week ending {week_ending}", ""]
    out.append("> ⚠️ Extractive mode (no LLM key set). Each day's top-10 list is "
               "reproduced as-is; no cross-week synthesis. Set `ANTHROPIC_API_KEY` "
               "for the full weekly wrap-up.")
    out.append("")
    for day, md in briefs:
        out.append(f"## {day}")
        top = _extract_top_section(md)
        out.append(top if top else "_No top-10 section found in this day's brief._")
        out.append("")
    return "\n".join(out)


def _extract_top_section(markdown: str) -> str:
    """Pull the '## 1. The 10 things...' block out of a daily brief."""
    for block in markdown.split("\n## ")[1:]:
        if block.lower().startswith("1."):
            body = block.split("\n", 1)
            return body[1].strip() if len(body) > 1 else ""
    return ""


def generate_weekly(days: int = 7) -> tuple[str | None, int]:
    """Build the weekly brief. Returns (markdown, n_days_found); markdown is None
    when there are no archives to summarise."""
    briefs = load_archives(days=days)
    if not briefs:
        return None, 0
    week_ending = now_local().strftime("%-d %B %Y")
    markdown = render_weekly(briefs, week_ending)
    if not markdown:
        markdown = render_weekly_fallback(briefs, week_ending)
    return markdown, len(briefs)
