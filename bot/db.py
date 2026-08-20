"""SQLite connection helper for the bot service.

Duplicated (not imported) from dashboard/db.py -- the two services are
separate Docker images, not an npm/pip workspace, so this mirrors the small
amount of shared schema by hand rather than adding a shared package for a
few lines.
"""

import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "idea_vault.sqlite"
IMAGES_DIR = DATA_DIR / "images"

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK(source_type IN ('text', 'url', 'screenshot')),
    raw_content TEXT,
    image_path TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processed', 'error')),
    summary TEXT,
    category TEXT,
    error_message TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    """Open a connection with the busy_timeout pragma set.

    Deliberately the default rollback journal, not WAL. Not a proven
    WAL-breaks-here case -- bot and dashboard share a Docker named volume
    (not a bind-mounted host path), so both are just two processes under the
    same kernel, WAL's ordinary case. The real reason: rollback journal only
    needs plain file locks (a lower bar than WAL's mmap-shared-memory
    coherence requirement), and this app's write volume makes WAL's actual
    benefit worth nothing -- so the mechanism with fewer assumptions was
    free. See this repo's TECH_STACK.md / CLAUDE.md for the fuller version.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    return conn


def distinct_categories(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT category FROM entries WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()
    return [row["category"] for row in rows]
