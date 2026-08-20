"""Read-only dashboard: cards grouped by category, plain-text search.

No auth -- deliberately LAN-only for v1 (see CLAUDE.md). Reads the same
SQLite file the bot service writes to.
"""

import sqlite3
from pathlib import Path

from db import IMAGES_DIR, get_connection
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Idea Vault Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


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
    finally:
        conn.close()

    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        if row["status"] == "processed":
            label = row["category"] or "Uncategorized"
        elif row["status"] == "pending":
            label = "Processing…"
        else:
            label = "Needs attention"
        grouped.setdefault(label, []).append(row)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "grouped": grouped, "query": q, "total": len(rows)},
    )
