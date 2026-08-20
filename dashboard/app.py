"""Read-only dashboard: cards grouped by category, plain-text search.

No auth -- deliberately LAN-only for v1 (see CLAUDE.md). Reads the same
SQLite file the bot service writes to.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from db import IMAGES_DIR, get_connection
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Idea Vault Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


def _display_timestamp(raw: str) -> str:
    """Format a stored ISO-8601 UTC timestamp for quiet display on a card.

    Falls back to the raw stored string if it doesn't parse. Deliberately
    NOT a relative-time ("3h ago") library: this is a static Jinja2 render
    with no JS to keep it live-updating, so a stale "3h ago" that was
    actually true 6 hours ago would be more misleading than a plain
    timestamp. Zero-padded numeric format (not "%-d"/"%#d" month-day
    shorthand) on purpose -- those directives aren't portable between the
    Linux container this runs in and Windows, where local dev happens.
    """
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return raw or ""
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _hostname(url: str) -> str:
    """Extract a bare, display-friendly hostname from a captured URL.

    Returns "" if `url` doesn't parse into something that actually looks
    like a host (no dot, e.g. free-text that got mis-tagged as source_type
    'url' upstream) -- the template only renders the clickable link pill
    when this is non-empty, and falls back to plain original-text
    otherwise. Without this check, garbage input like a pasted sentence
    would still render as a live-looking <a href> pointing at a broken
    relative path, which is worse than not linkifying it at all. Strips a
    leading "www." since it adds no information for a personal list.

    Also rejects any non-http(s) scheme (e.g. "javascript:"). Not reachable
    today -- bot/main.py only ever sets source_type='url' for text starting
    with http(s)://, so every caller is currently safe by inheriting that
    invariant -- but the template renders raw_content verbatim as a real
    href, and this function's own job is deciding what's safe to linkify,
    so it shouldn't depend on an invariant it doesn't itself enforce.
    """
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"//{url}")
    if parsed.scheme not in ("", "http", "https"):
        return ""
    host = parsed.netloc
    if "." not in host and host != "localhost":
        return ""
    return host.removeprefix("www.")


def _display_label(status: str, category: str | None) -> str:
    """Single source of truth for what to call an entry's bucket.

    Used for BOTH the per-card chip and the section-grouping key in
    index() -- they used to be computed separately (a near-duplicate but
    not-quite-identical branch in each place) and had already drifted: an
    errored entry with no category showed chip "Uncategorized" while its
    own section header read "Needs attention" -- visibly contradictory on
    the exact feature (status visibility) this was built for. One function,
    used both places, makes that class of drift impossible instead of just
    unlikely.
    """
    if status == "processed":
        return category or "Uncategorized"
    if status == "pending":
        return "Processing…"
    return "Needs attention"


def _enrich(row: sqlite3.Row) -> dict:
    """Attach display-only derived fields to a raw `entries` row.

    Computed here, not in the template, so Jinja stays a dumb renderer --
    hostname extraction and timestamp formatting are real logic even though
    they only feed presentation. No schema changes: every source field
    (source_type, raw_content, image_path, status, summary, category,
    error_message, created_at) already exists on the table, this just adds
    derived keys alongside them.
    """
    item = dict(row)
    item["display_time"] = _display_timestamp(item["created_at"])
    item["display_category"] = _display_label(item["status"], item["category"])
    item["hostname"] = (
        _hostname(item["raw_content"])
        if item["source_type"] == "url" and item["raw_content"]
        else ""
    )
    return item


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "") -> HTMLResponse:
    conn = get_connection()
    try:
        if q:
            pattern = f"%{q}%"
            rows = conn.execute(
                """
                SELECT * FROM entries
                WHERE raw_content LIKE ? OR summary LIKE ? OR category LIKE ?
                ORDER BY created_at DESC
                """,
                (pattern, pattern, pattern),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM entries ORDER BY created_at DESC").fetchall()
        vault_total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    finally:
        conn.close()

    entries = [_enrich(row) for row in rows]

    grouped: dict[str, list[dict]] = {}
    for item in entries:
        grouped.setdefault(item["display_category"], []).append(item)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "grouped": grouped,
            "query": q,
            "total": len(entries),
            "vault_total": vault_total,
        },
    )
