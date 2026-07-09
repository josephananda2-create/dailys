"""The fallback renderer + markdown→html must always produce output."""
from datetime import datetime, timezone

from morning_brief.models import Item
from morning_brief.pipeline.deliver import _markdown_to_html
from morning_brief.pipeline.generate import _render_fallback
from tests.test_pipeline import make_cfg


def _item(title, section, category):
    return Item(title=title, url="http://x/" + title.replace(" ", "-"), source_name="Src",
                category=category, section=section, published=datetime.now(timezone.utc),
                summary="short snippet", reliability=9, priority=8)


def test_fallback_renders_all_ten_sections_even_when_empty():
    cfg = make_cfg()
    md = _render_fallback([], [], cfg, {"failed": []})
    for heading in ["# Morning Brief", "## 1.", "## 5.", "## 8.", "## 10."]:
        assert heading in md


def test_fallback_includes_items_and_sources():
    cfg = make_cfg()
    items = [_item("Proton unveils EV", "client_category", "automotive")]
    md = _render_fallback(items, [], cfg, {"failed": []})
    assert "Proton unveils EV" in md
    assert "http://x/Proton-unveils-EV" in md


def test_markdown_to_html_links_and_bold():
    html = _markdown_to_html("## Head\n- **Bold** and [link](http://a.com)\n")
    assert "<h2>Head</h2>" in html
    assert "<strong>Bold</strong>" in html
    assert '<a href="http://a.com">link</a>' in html
