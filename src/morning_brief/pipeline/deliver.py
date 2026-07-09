"""Delivery: write brief to disk archive, save to Notion, optionally email."""
from __future__ import annotations

import re
from pathlib import Path

from ..config_loader import Config
from ..connectors import gmail
from ..connectors import notion as notion_conn
from ..utils.dates import today_iso, today_str
from ..utils.logging import get_logger

log = get_logger()


def save_local(markdown: str, archive_dir: str | Path = "data/archive") -> Path:
    d = Path(archive_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"brief-{today_iso()}.md"
    path.write_text(markdown, encoding="utf-8")
    log.info("Brief written to %s", path)
    return path


def save_to_notion(markdown: str, n_sections: int, n_items: int) -> str | None:
    return notion_conn.save_brief(
        title=f"Morning Brief — {today_str()}",
        date_iso=today_iso(),
        markdown=markdown,
        n_sections=n_sections,
        n_items=n_items,
    )


def email_brief(markdown: str, cfg: Config) -> bool:
    html = _markdown_to_html(markdown)
    subject = f"☀️ Morning Brief — {today_str()}"
    return gmail.send_email(subject, html)


def _markdown_to_html(md: str) -> str:
    """Minimal, dependency-free Markdown → HTML for email."""
    lines = md.splitlines()
    html: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    for line in lines:
        s = line.rstrip()
        if not s.strip():
            close_list()
            continue
        s_html = _inline(s)
        if s.startswith("### "):
            close_list(); html.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("## "):
            close_list(); html.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("# "):
            close_list(); html.append(f"<h1>{_inline(s[2:])}</h1>")
        elif s.startswith("> "):
            close_list(); html.append(f"<blockquote>{_inline(s[2:])}</blockquote>")
        elif s.lstrip().startswith(("- ", "* ")):
            if not in_list:
                html.append("<ul>"); in_list = True
            html.append(f"<li>{_inline(s.lstrip()[2:])}</li>")
        elif s.startswith("---"):
            close_list(); html.append("<hr>")
        else:
            close_list(); html.append(f"<p>{s_html}</p>")
    close_list()
    body = "\n".join(html)
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:720px;margin:0 auto;line-height:1.5;color:#1a1a1a">' + body + "</div>"
    )


def _inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)
    return text
