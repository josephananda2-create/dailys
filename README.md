# ☀️ Morning Brief

An automated daily briefing system for an advertising strategist. Every morning
at **07:00 Asia/Kuala_Lumpur** it collects from your sources (RSS, Gmail,
Google Calendar, news APIs), scores and de-duplicates the material, has an LLM
write a sharp 10-section brief, archives it to Notion, and emails it to you.

Built to be **simple, reliable, and modular**. It degrades gracefully: with zero
credentials it still produces a real brief from public RSS. Add integrations one
at a time.

---

## How it works

```
config/*.yaml ──► collect ──► dedupe ──► score ──► filter-seen ──► generate ──► deliver
  (sources,        (RSS,       (fuzzy    (relevance   (cross-day    (LLM or      (disk +
   categories,      Gmail,      title     weights)     memory)       extractive   Notion +
   scoring)         Calendar,   clusters)                            fallback)    email)
                    NewsAPI)
```

- **Sources are never hardcoded** — they live entirely in `config/sources.yaml`.
- **The LLM only summarises items we actually fetched** (each with a real
  title / source / url / date). It is instructed never to add facts not present.
  That is the core guardrail against hallucinated claims and fake citations.
- **A source failing is logged and skipped** — it never stops the run.

### The 8 sections
1. The 10 things you need to know today
2. Advertising & strategy radar
3. World radar
4. Malaysia radar
5. Client category watch (grouped, with strategic implications)
6. AI watch
7. Sports corner
8. My day ahead (Calendar + flagged emails) → plus a **Strategist's takeaway**
   and a full **source list**.

---

## Quick start (60 seconds, no credentials)

```bash
python -m venv .venv && source .venv/bin/activate
pip install ".[all]"          # or just: pip install .   (RSS-only)
brief sources validate         # check your config
brief preview                  # generate a brief to your terminal
```

With no `ANTHROPIC_API_KEY`, you get an **extractive** brief: real headlines and
sources, no AI synthesis. Add the key for the full written brief.

> **Note on this repo's dev sandbox:** outbound fetches to arbitrary feed hosts
> may be blocked by a network proxy. Run locally or in GitHub Actions for live
> feeds.

---

## Commands

| Command | What it does |
|---|---|
| `brief run [--email]` | Full pipeline: generate → save locally → save to Notion → (optional email). This is what the scheduler runs. |
| `brief preview [--out FILE] [--include-seen]` | Generate and print/write. No Notion, no email. |
| `brief send` | Generate and email the brief. |
| `brief save` | Generate and save to Notion. |
| `brief sources validate` | Validate `config/sources.yaml`. |
| `brief sources list` | List all sources with status/priority/reliability. |
| `brief logs [-n N]` | Show today's log file. |
| `brief test` | Ping every integration and report what's configured. |

(You can also invoke as `python -m morning_brief.main …` without installing.)

---

## Configuration — you mainly edit YAML

### `config/sources.yaml`  ← add/remove/pause/prioritise sources here
Each source supports: `name, type, category, region, url|query, priority (1-10),
reliability (1-10), frequency, tags, active, notes`.

- `type`: `rss | website | newsletter | api | gmail_search | manual | youtube | podcast | social`
- `active: false` → skipped entirely.
- **High `priority`** → more weight in ranking.
- **Low `reliability`** (< threshold in `scoring.yaml`) → only included if a
  second source corroborates the story.
- `tags` that match today's calendar/inbox topics → that source's items get a
  same-day relevance boost.
- URLs left as `ADD_..._HERE` are placeholders: the validator **warns** and the
  collector **skips** them. Fill them in as you find the real feed URLs.

Validate any time with `brief sources validate`. It also runs automatically
before every `brief run`.

### `config/categories.yaml`  ← your categories + client watchlist
Maps each category to a newsletter section and keyword hints, and lists your
**clients/competitors** so their brand mentions get a scoring boost and get
flagged in the "Client category watch" section. Edit the `watchlist:` block with
your real client names.

### `config/scoring.yaml`  ← ranking & dedupe rules
Tune weights (priority, reliability, freshness, category match, watchlist match,
calendar match, corroboration), the freshness half-life, max item age, the
low-reliability threshold, dedupe similarity, the cross-day "seen" window, and
per-section caps. No code changes needed.

---

## Credentials & setup (all optional, add incrementally)

Copy `.env.example` to `.env` and fill in what you have.

### 1. Anthropic (the written brief) — *recommended first*
- Get a key from the Anthropic Console → `ANTHROPIC_API_KEY`.
- Optional: `BRIEF_MODEL` (default `claude-sonnet-5`).
- Without it, the brief runs in extractive mode.

### 2. Notion (archive + saved insights + seen-story log)
1. Create an internal integration at <https://www.notion.so/my-integrations>,
   copy its secret → `NOTION_API_KEY`.
2. Create (or pick) a Notion page to hold the brief, **share it with your
   integration** (⋯ → Connections → your integration).
3. Copy that page's 32-char id from its URL → `NOTION_PARENT_PAGE_ID`.
4. On first run the app auto-creates two databases under that page:
   **Morning Brief Archive** and **Seen Stories Log**.

> Design choice: your **source list and watchlist live in the YAML files** (one
> source of truth, versioned in git). Notion stores the **outputs** — the daily
> briefs and the running seen-story log.

### 3. Google (Gmail scan + Calendar + email send)
One OAuth client covers all three.
1. Google Cloud Console → new project → enable **Gmail API** and **Calendar API**.
2. Create an **OAuth client ID → Desktop app**. Copy id/secret to
   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
3. Mint a refresh token:
   ```bash
   pip install ".[google]"
   GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python scripts/google_auth.py
   ```
   Paste the printed value into `GOOGLE_REFRESH_TOKEN`.
4. Set `BRIEF_RECIPIENT` (defaults to your Gmail account).

### 4. NewsAPI (optional) — for `type: api` sources
Get a key at <https://newsapi.org> → `NEWSAPI_KEY`.

Run `brief test` to see exactly what's configured.

---

## Scheduling — runs every day at 07:00 MYT

### Option A (recommended): GitHub Actions — already included
`.github/workflows/daily-brief.yml` runs at `23:00 UTC` (= `07:00` Kuala Lumpur)
daily, and on-demand from the Actions tab.

1. Push this repo to GitHub.
2. Repo → **Settings → Secrets and variables → Actions** → add the same keys
   from your `.env` as repository secrets (`ANTHROPIC_API_KEY`, `NOTION_API_KEY`,
   `NOTION_PARENT_PAGE_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GOOGLE_REFRESH_TOKEN`, `BRIEF_RECIPIENT`, optionally `BRIEF_MODEL`,
   `NEWSAPI_KEY`).
3. Done. It emails you each morning, archives to Notion, and uploads the brief +
   logs as a run artifact. Dedupe memory persists between runs via Actions cache.

### Option B: local cron
```cron
# crontab -e   (server set to Asia/Kuala_Lumpur, or adjust the hour)
0 7 * * *  cd /path/to/dailys && /path/to/.venv/bin/brief run --email >> data/logs/cron.log 2>&1
```

---

## Project structure

```
config/         sources.yaml · categories.yaml · scoring.yaml   ← you edit these
src/morning_brief/
  main.py                  CLI (run/preview/send/save/sources/logs/test)
  config_loader.py         load + validate YAML
  models.py                Source, Item
  connectors/              rss · gmail · calendar · news · notion · google_auth
  pipeline/                collect · dedupe · score · summarize · generate · deliver · seen_store
  utils/                   logging · dates · text
scripts/google_auth.py     one-time Google refresh-token minter
data/                       cache/ · logs/ · archive/ (git-ignored contents)
tests/                      pytest suite
.github/workflows/daily-brief.yml   the 07:00 MYT scheduler
```

---

## Guardrails (built in)
- Never invents facts — the LLM is constrained to summarise fetched items only.
- Every factual claim carries a source link + date; a full source list closes the brief.
- Rumours/unconfirmed items are labelled.
- Cross-day de-duplication: a story isn't repeated unless it materially updated.
- Low-reliability single sources are held back until corroborated.
- Blunt, non-sycophantic editorial tone (set in the system prompt).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `brief` not found | `pip install .` (or use `python -m morning_brief.main …`). |
| A source shows in logs as failed | Normal if a feed is down/blocked — the run continues. Check the URL, or `active: false` it. |
| Brief is in "extractive mode" | Set `ANTHROPIC_API_KEY`. |
| Nothing saved to Notion | Set `NOTION_API_KEY` + `NOTION_PARENT_PAGE_ID`, and **share the page with the integration**. |
| Gmail/Calendar empty | Re-run `scripts/google_auth.py`; confirm both APIs are enabled; check `brief test`. |
| Feed won't parse | Some "website" sources aren't real feeds — find the site's `/feed` or `/rss` URL. |
| `sgmllib3k` build error on install | Environment-specific (old system setuptools). Use a fresh venv, or the app falls back to a built-in stdlib RSS parser. |
| Wrong time | Set `TZ=Asia/Kuala_Lumpur`; the GitHub cron is already `23:00 UTC`. |
| See what happened | `brief logs` (or `data/logs/brief-YYYY-MM-DD.log`). |

---

## Development
```bash
pip install ".[dev]"
pytest -q
```

## Roadmap (kept modular for expansion)
- Per-section LLM passes for deeper synthesis on heavy news days.
- Podcast/YouTube transcript ingestion for the strategy section.
- A Notion "Saved Insights" inbox the brief can pull from and write back to.
- Slack/Telegram delivery connector alongside email.
```
Add sources by editing config/sources.yaml — no code changes required.
```
