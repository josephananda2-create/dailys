"""LLM summarisation + insight extraction (Anthropic).

The model is given ONLY the items we actually fetched (title/source/url/date/
snippet). It must summarise and cite from that set — it is explicitly forbidden
to add facts not present. This is the core anti-hallucination guardrail.

Returns markdown, or None if the LLM isn't configured/available (caller then
falls back to the deterministic extractive renderer in generate.py).
"""
from __future__ import annotations

import json

from ..config_loader import env
from ..utils.logging import get_logger

log = get_logger()

SYSTEM_PROMPT = """\
You are the editor of a daily morning brief for a senior advertising strategist \
in Malaysia. Your reader is smart and time-poor. Write sharp, plain, useful \
English a 10-year-old could follow but a senior strategist still respects.

ABSOLUTE RULES:
- Use ONLY the items provided in the input JSON. Never invent facts, numbers, \
quotes, or events. If something is not in the items, do not say it.
- Every factual claim must map to one of the provided items. Cite as \
[Source name, YYYY-MM-DD](url) using the item's real source, date and url.
- If an item is a rumour/unconfirmed, label it "(unconfirmed)".
- Deduplicate: never repeat the same story twice.
- Be blunt when something is overhyped or strategically weak. No fluff, no \
clickbait, no hype, no sycophancy toward any brand/agency/platform.
- Keep "why it matters" concrete and specific — no filler.
- BALANCE: do not let one brand or category dominate. If several items are about \
the same brand (e.g. one carmaker), pick the best ONE and move on. Spread \
attention across what's provided.
- NEVER mention feeds, fetching, sources failing, "blind spots", or any system/\
plumbing detail. You are an editor, not a status report. If a section is genuinely \
thin, write ONE neutral line (e.g. "Quiet day here.") and move on — never explain why.

Return GitHub-flavoured Markdown ONLY, following the exact section structure \
requested. Do not add a preamble or sign-off.
"""

USER_TEMPLATE = """\
Date: {date}

Here is today's material as JSON. Each item is a real, fetched source.
```json
{payload}
```

Produce the brief with EXACTLY these sections and headings:

# Morning Brief: {date}

## 1. The 10 things you need to know today
Ten most important items across everything (use the "top_picks" ids as a guide \
but you may adjust for balance). Each: **Headline** — simple explanation — why it \
matters — source link.

## 2. Advertising and strategy radar
Sub-group: **Advertising moves**, **Strategy thinking**, **Campaigns worth studying**, \
**Tools or ways of working**. For each item: what happened / why it matters / how I \
can use this in my work. For strategy items, extract the applicable THINKING, not just news.

## 3. World radar
Global business, politics, economics, markets, culture, tech. Each: explain simply / \
why it matters / what to watch next.

## 4. Malaysia radar
Same format, focused on Malaysia and useful for Malaysian brand strategy.

## 5. Client category watch
Group by category (Automotive, FMCG, Oil & gas / energy, Sustainability, Alcohol, \
Entertainment, Telco, Banking, Other). For each: key update / brand or competitor / \
strategic implication / possible slide angle or talking point. Flag which client it may affect.

## 6. AI watch
Sub-group: **Big AI news**, **Useful tools**, **Policy / regulation**, \
**Agency / workflow implications**, **What I should try**. Be practical — say what to try and what to ignore.

## 7. Sports corner
Concise and fun: MMA/UFC/ONE, BJJ, F1, football. Upcoming, results, storylines, moves.

## 8. My day ahead
If "has_calendar" is true, use the calendar events: what I have today and tomorrow, \
what to prepare, and any news above that connects to a meeting. If "has_calendar" is \
false, write exactly one neutral line: "Calendar not connected yet — connect Google \
Calendar to see today's meetings here." Do NOT mention feeds or fetching.

## 9. Strategist's takeaway
3-5 sharp, marketing/communications-STRATEGY observations — the kind Mark Pollard, \
Julian Cole, WARC or Strategy Cold Cuts would post: a fresh POV, a hot take, a reframe, \
a "so what" for brands. Prefer angles drawn from the advertising/strategy items. \
Each: what it means / how to use it (brief, deck, pitch, client convo) / which client or category it applies to.

## 10. Source list
Bullet every source cited above, as [Name, date](url). Every claim must trace here.
"""


def render_with_llm(context: dict) -> str | None:
    api_key = env("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("ANTHROPIC_API_KEY not set — using extractive fallback renderer.")
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic not installed; run `pip install .[llm]`.")
        return None

    model = env("BRIEF_MODEL") or "claude-sonnet-5"
    payload = json.dumps(context, ensure_ascii=False, indent=1)
    # Keep payload bounded to control cost/latency.
    if len(payload) > 120_000:
        payload = payload[:120_000] + "\n… (truncated)"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_TEMPLATE.format(date=context["date"], payload=payload),
            }],
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        log.info("LLM brief generated with %s (%d chars).", model, len(text))
        return text.strip()
    except Exception as exc:  # noqa: BLE001
        log.error("LLM generation failed (%s); falling back. ", exc)
        return None
