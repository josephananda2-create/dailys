"""Morning Brief CLI.

Commands:
  brief run             Full pipeline: collect → generate → save local + Notion (+ email if --email)
  brief preview         Generate and print/write to disk. No Notion, no email.
  brief send            Generate and email the brief.
  brief save            Generate and save to Notion.
  brief weekly          Synthesise the past week's daily briefs (+ email if --email).
  brief sources validate   Validate config/sources.yaml.
  brief sources list       List configured sources and their status.
  brief logs               Show today's log file.
  brief test               Test each integration (Notion, Gmail, Calendar, LLM).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config_loader import env, load_config, validate_sources
from .utils.dates import today_iso
from .utils.logging import get_logger, setup_logging

log = get_logger()


# --- tiny .env loader (no extra dependency) ----------------------------------
def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# --- pipeline runner ---------------------------------------------------------
def _run_pipeline(root: str, save_notion: bool, do_email: bool, write_local: bool) -> int:
    from .pipeline import dedupe, generate, score
    from .pipeline.collect import collect
    from .pipeline.deliver import email_brief, save_local, save_to_notion
    from .pipeline.seen_store import SeenStore
    from .connectors import calendar as cal_conn
    from .connectors import gmail as gmail_conn

    cfg = load_config(root)

    # Validate before running; warn but don't abort on soft issues.
    vr = validate_sources(root)
    for e in vr.errors:
        log.error("sources.yaml: %s", e)
    if vr.errors:
        log.error("Aborting: fix sources.yaml errors first (`brief sources validate`).")
        return 2
    for w in vr.warnings:
        log.warning("sources.yaml: %s", w)

    items, events, report = collect(cfg)

    # Cross-signal boosts.
    calendar_words = cal_conn.meeting_keywords(events)
    inbox_topics: set[str] = set()
    try:
        inbox_topics = gmail_conn.inbox_topics(cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("inbox topic scan skipped: %s", exc)

    # Dedupe → score → filter-seen.
    dd = cfg.scoring.get("dedupe", {})
    store = SeenStore(
        window_days=dd.get("seen_window_days", 5),
        similarity_threshold=dd.get("title_similarity", 0.72),
    )
    items = dedupe.dedupe_within_run(items, cfg)
    scored = score.score_items(items, cfg, calendar_words, inbox_topics)
    scored = dedupe.filter_seen(scored, cfg, store)

    markdown, context = generate.generate(scored, events, cfg, report)

    if write_local:
        save_local(markdown)

    if save_notion:
        n_items = sum(len(v) for v in context["sections"].values())
        url = save_to_notion(markdown, n_sections=len(context["sections"]), n_items=n_items)
        if url:
            log.info("Notion archive: %s", url)
        # Persist seen-story memory (local + Notion).
        added = store.add_many(scored)
        store.save()
        try:
            from .connectors import notion as notion_conn
            notion_conn.append_seen([
                {"title": r["title"], "url": r["url"], "date": None, "category": r["category"]}
                for r in added
            ])
        except Exception as exc:  # noqa: BLE001
            log.warning("seen-log to Notion skipped: %s", exc)

    if do_email:
        email_brief(markdown, cfg)

    # Always show a run summary.
    failed = report.get("failed", [])
    log.info("Done. %d items in brief. %d sources failed.%s",
             sum(len(v) for v in context["sections"].values()),
             len(failed),
             (" (" + ", ".join(f["name"] for f in failed) + ")") if failed else "")
    return 0


# --- individual commands -----------------------------------------------------
def cmd_run(args):
    return _run_pipeline(args.root, save_notion=True, do_email=args.email, write_local=True)


def cmd_preview(args):
    from .pipeline import dedupe, generate, score
    from .pipeline.collect import collect
    from .pipeline.seen_store import SeenStore

    cfg = load_config(args.root)
    items, events, report = collect(cfg)
    items = dedupe.dedupe_within_run(items, cfg)
    scored = score.score_items(items, cfg)
    if not args.include_seen:
        store = SeenStore(window_days=cfg.scoring.get("dedupe", {}).get("seen_window_days", 5))
        scored = dedupe.filter_seen(scored, cfg, store)
    markdown, _ = generate.generate(scored, events, cfg, report)

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print("\n" + markdown)
    return 0


def cmd_send(args):
    return _run_pipeline(args.root, save_notion=False, do_email=True, write_local=True)


def cmd_save(args):
    return _run_pipeline(args.root, save_notion=True, do_email=False, write_local=True)


def cmd_weekly(args):
    from .pipeline import weekly
    from .pipeline.deliver import email_markdown, save_local

    markdown, n_days = weekly.generate_weekly(days=args.days)
    if not markdown:
        log.error("No daily briefs found in data/archive for the last %d days — "
                  "nothing to summarise.", args.days)
        return 1
    log.info("Weekly brief built from %d daily brief(s).", n_days)
    save_local(markdown, filename=f"weekly-{today_iso()}.md")
    if args.email:
        from .utils.dates import now_local
        subject = f"📅 Weekly Brief — week ending {now_local().strftime('%-d %B %Y')}"
        email_markdown(markdown, subject)
    else:
        print("\n" + markdown)
    return 0


def cmd_sources(args):
    if args.action == "validate":
        vr = validate_sources(args.root)
        for e in vr.errors:
            print(f"  ERROR:   {e}")
        for w in vr.warnings:
            print(f"  warning: {w}")
        if vr.ok:
            print(f"✓ sources.yaml is valid ({len(vr.warnings)} warning(s)).")
            return 0
        print(f"✗ sources.yaml has {len(vr.errors)} error(s).")
        return 1
    if args.action == "list":
        cfg = load_config(args.root)
        print(f"{'STATUS':8} {'PRI':>3} {'REL':>3}  {'TYPE':13} {'CATEGORY':22} NAME")
        for s in cfg.sources:
            status = "active" if s.active else "PAUSED"
            print(f"{status:8} {s.priority:>3} {s.reliability:>3}  {s.type:13} {s.category:22} {s.name}")
        active = sum(1 for s in cfg.sources if s.active)
        print(f"\n{active}/{len(cfg.sources)} active.")
        return 0
    return 1


def cmd_logs(args):
    log_file = Path("data/logs") / f"brief-{today_iso()}.log"
    if not log_file.exists():
        print(f"No log for today ({log_file}). Run a brief first.")
        return 1
    text = log_file.read_text()
    lines = text.splitlines()
    tail = lines[-args.lines:] if args.lines else lines
    print("\n".join(tail))
    return 0


def cmd_test(args):
    from .connectors import calendar as cal_conn
    from .connectors import gmail as gmail_conn
    from .connectors import notion as notion_conn
    from .connectors.base import ConnectorStatus

    print("Testing integrations…\n")
    results = []

    # LLM
    if env("ANTHROPIC_API_KEY"):
        results.append(ConnectorStatus("Anthropic (LLM)", True, f"key set, model={env('BRIEF_MODEL','claude-sonnet-5')}"))
    else:
        results.append(ConnectorStatus("Anthropic (LLM)", False, "no ANTHROPIC_API_KEY — extractive fallback mode"))

    # Notion
    try:
        ok = notion_conn.available()
        results.append(ConnectorStatus("Notion", ok, "configured" if ok else "no NOTION_API_KEY / parent page"))
    except Exception as exc:  # noqa: BLE001
        results.append(ConnectorStatus("Notion", False, str(exc)))

    # Email (SMTP App Password preferred, else Gmail API)
    try:
        from .connectors import smtp_mail
        if smtp_mail.configured():
            results.append(ConnectorStatus("Email (SMTP)", True, f"app password set, to {env('BRIEF_RECIPIENT') or env('SMTP_USER')}"))
        else:
            ok = gmail_conn.available()
            results.append(ConnectorStatus("Email (Gmail API)", ok, "authenticated" if ok else "not configured (set SMTP_APP_PASSWORD for simple email)"))
    except Exception as exc:  # noqa: BLE001
        results.append(ConnectorStatus("Email", False, str(exc)))

    # Gmail inbox scan (OAuth only)
    google_hint = ("token set but refresh failed — likely expired (Testing-mode "
                   "tokens last 7 days); see README 'Google setup'"
                   if env("GOOGLE_REFRESH_TOKEN") else None)
    try:
        ok = gmail_conn.available()
        results.append(ConnectorStatus("Gmail inbox scan", ok,
                                       "authenticated" if ok else (google_hint or "not configured (optional, OAuth)")))
    except Exception as exc:  # noqa: BLE001
        results.append(ConnectorStatus("Gmail inbox scan", False, str(exc)))

    # Calendar
    try:
        ok = cal_conn.available()
        results.append(ConnectorStatus("Google Calendar", ok,
                                       "authenticated" if ok else (google_hint or "not configured")))
    except Exception as exc:  # noqa: BLE001
        results.append(ConnectorStatus("Google Calendar", False, str(exc)))

    # RSS reachability (one quick probe)
    try:
        from .connectors import rss as rss_conn
        cfg = load_config(args.root)
        rss_src = next((s for s in cfg.sources if s.type == "rss" and s.active
                        and s.url and not s.url.startswith("ADD_")), None)
        if rss_src:
            got = rss_conn.fetch(rss_src, cfg)
            engine = "feedparser" if rss_conn._HAVE_FEEDPARSER else "stdlib"
            results.append(ConnectorStatus("RSS (probe)", bool(got),
                                           f"{rss_src.name}: {len(got)} items ({engine})"))
        else:
            results.append(ConnectorStatus("RSS (probe)", False, "no usable RSS source configured"))
    except Exception as exc:  # noqa: BLE001
        results.append(ConnectorStatus("RSS (probe)", False, str(exc)))

    for r in results:
        print(r)
    print("\nNote: missing integrations degrade gracefully — the brief still runs on what's available.")
    return 0


# --- arg parsing -------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brief", description="Automated daily morning brief.")
    p.add_argument("--root", default=".", help="Project root (default: current dir).")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="Full pipeline: generate, save local + Notion.")
    r.add_argument("--email", action="store_true", help="Also email the brief.")
    r.set_defaults(func=cmd_run)

    pv = sub.add_parser("preview", help="Generate and print/write. No send, no save.")
    pv.add_argument("--out", help="Write markdown to this file instead of stdout.")
    pv.add_argument("--include-seen", action="store_true", help="Don't filter previously-seen stories.")
    pv.set_defaults(func=cmd_preview)

    s = sub.add_parser("send", help="Generate and email the brief.")
    s.set_defaults(func=cmd_send)

    sv = sub.add_parser("save", help="Generate and save to Notion.")
    sv.set_defaults(func=cmd_save)

    wk = sub.add_parser("weekly", help="Synthesise the past week's daily briefs.")
    wk.add_argument("--email", action="store_true", help="Email the weekly brief.")
    wk.add_argument("--days", type=int, default=7, help="How many days back to include (default 7).")
    wk.set_defaults(func=cmd_weekly)

    src = sub.add_parser("sources", help="Work with sources.yaml.")
    src.add_argument("action", choices=["validate", "list"])
    src.set_defaults(func=cmd_sources)

    lg = sub.add_parser("logs", help="Show today's log.")
    lg.add_argument("-n", "--lines", type=int, default=200, help="Tail this many lines (0 = all).")
    lg.set_defaults(func=cmd_logs)

    t = sub.add_parser("test", help="Test integrations.")
    t.set_defaults(func=cmd_test)

    return p


def main(argv=None) -> int:
    _load_dotenv()
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        log.warning("Interrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001
        log.exception("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
