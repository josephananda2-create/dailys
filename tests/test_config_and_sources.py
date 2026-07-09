"""Validate the shipped config + the validator itself."""
from pathlib import Path

from morning_brief.config_loader import load_config, validate_sources

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_sources_validate_without_errors():
    vr = validate_sources(ROOT)
    assert vr.ok, f"sources.yaml has errors: {vr.errors}"


def test_load_config_parses_sources_and_categories():
    cfg = load_config(ROOT)
    assert len(cfg.sources) > 5
    assert "advertising" in cfg.categories
    # section resolution works
    assert cfg.section_for("ai") == "ai"
    assert cfg.section_for("automotive") == "client_category"


def test_gmail_source_requires_query(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(
        "sources:\n"
        "  - name: Bad Gmail\n"
        "    type: gmail_search\n"
        "    category: advertising\n"
    )
    (tmp_path / "config" / "categories.yaml").write_text("categories:\n  advertising:\n    section: advertising\n")
    (tmp_path / "config" / "scoring.yaml").write_text("weights: {}\n")
    vr = validate_sources(tmp_path)
    assert any("query" in w for w in vr.warnings)


def test_invalid_type_is_error(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(
        "sources:\n  - name: X\n    type: carrier_pigeon\n    category: advertising\n    url: http://x\n"
    )
    (tmp_path / "config" / "categories.yaml").write_text("categories: {}\n")
    (tmp_path / "config" / "scoring.yaml").write_text("weights: {}\n")
    vr = validate_sources(tmp_path)
    assert not vr.ok
    assert any("invalid type" in e for e in vr.errors)
