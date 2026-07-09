"""Unit tests for dedupe, scoring, and the seen store."""
from datetime import datetime, timedelta, timezone

from morning_brief.config_loader import Config
from morning_brief.models import Item
from morning_brief.pipeline import dedupe, score
from morning_brief.pipeline.seen_store import SeenStore
from morning_brief.utils.text import normalize_title, similarity


def make_cfg():
    return Config(
        sources=[],
        categories={
            "advertising": {"section": "advertising", "keywords": ["agency", "campaign"]},
            "automotive": {"section": "client_category", "keywords": ["car", "ev"]},
        },
        watchlist=[{"client": "Auto client", "category": "automotive", "brands": ["Proton"], "competitors": []}],
        scoring={
            "weights": {"priority": 1.6, "reliability": 0.8, "freshness": 3.0,
                        "category_match": 2.0, "watchlist_match": 4.0, "corroboration": 2.0},
            "freshness_half_life_hours": 24, "max_age_hours": 72,
            "low_reliability_threshold": 6,
            "dedupe": {"title_similarity": 0.72, "seen_window_days": 5, "meaningful_update_delta": 0.35},
            "section_caps": {}, "top_n": 10,
        },
        root=".",
    )


def _item(title, **kw):
    kw.setdefault("published", datetime.now(timezone.utc))
    return Item(title=title, url=kw.pop("url", "http://x/" + title.replace(" ", "-")),
                source_name=kw.pop("source_name", "Src"), category=kw.pop("category", "advertising"),
                section=kw.pop("section", "advertising"), **kw)


def test_normalize_and_similarity():
    assert normalize_title("The Agency Wins a Pitch!") == "agency wins pitch"
    assert similarity("Proton launches new EV", "Proton launches a new EV") > 0.8
    assert similarity("Proton launches EV", "Football results tonight") < 0.4


def test_dedupe_clusters_similar_titles_and_records_corroboration():
    cfg = make_cfg()
    items = [
        _item("Proton launches new EV model", source_name="A", reliability=9),
        _item("Proton launches a new EV model!", source_name="B", reliability=7),
        _item("Totally different football news", source_name="C"),
    ]
    reps = dedupe.dedupe_within_run(items, cfg)
    assert len(reps) == 2
    ev = next(r for r in reps if "Proton" in r.title)
    assert ev.source_name == "A"  # higher reliability wins
    assert "B" in ev.corroborated_by


def test_low_reliability_dropped_unless_corroborated():
    cfg = make_cfg()
    weak = _item("Unbacked rumour about telco", source_name="Weak", reliability=3)
    scored = score.score_items([weak], cfg)
    assert scored == []  # dropped: low reliability, no corroboration, no watchlist


def test_watchlist_and_category_boost_scores():
    cfg = make_cfg()
    plain = _item("Some agency campaign news", category="advertising", reliability=9, priority=5)
    branded = _item("Proton unveils new car", category="automotive", section="client_category",
                    reliability=9, priority=5)
    ranked = score.score_items([plain, branded], cfg)
    branded_scored = next(i for i in ranked if "Proton" in i.title)
    assert branded_scored.watchlist_hits == ["Proton"]
    assert "watchlist_match" in branded_scored.score_breakdown


def test_watchlist_with_yaml_boolean_brand_does_not_crash():
    # Regression: a bare 'YES' in YAML parses to bool True; must not crash rendering.
    cfg = make_cfg()
    cfg.watchlist = [{"client": "Telco", "category": "telecommunications",
                      "brands": [True], "competitors": []}]
    from morning_brief.pipeline.score import _flatten_watchlist
    pairs = _flatten_watchlist(cfg)
    assert all(isinstance(b, str) for b, _ in pairs)
    item = _item("true story about something", reliability=9)
    ranked = score.score_items([item], cfg)  # must not raise
    from morning_brief.pipeline.generate import _item_line
    _item_line(ranked[0]) if ranked else None  # must not raise


def test_old_items_filtered_by_max_age():
    cfg = make_cfg()
    old = _item("Ancient news", reliability=9, published=datetime.now(timezone.utc) - timedelta(hours=200))
    assert score.score_items([old], cfg) == []


def test_seen_store_roundtrip_and_filter(tmp_path):
    cfg = make_cfg()
    path = tmp_path / "seen.json"
    store = SeenStore(path=path, window_days=5)
    story = _item("Proton launches new EV model", reliability=9)
    store.add_many([story])
    store.save()

    store2 = SeenStore(path=path, window_days=5)
    # Same story again → filtered out (no meaningful change).
    again = _item("Proton launches new EV model", reliability=9)
    kept = dedupe.filter_seen([again], cfg, store2)
    assert kept == []
