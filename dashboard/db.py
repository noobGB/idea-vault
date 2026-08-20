"""SQLite connection helper for the dashboard service.

Duplicated (not imported) from bot/db.py -- the two services are separate
Docker images, not an npm/pip workspace, so this mirrors the small amount of
shared schema by hand rather than adding a shared package for a few lines.
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

    Deliberately the default rollback journal, not WAL -- this file is opened
    by two separate containers (bot + dashboard), which is the same
    cross-process-over-a-virtualized-share shape that breaks WAL's
    shared-memory coordination. See this repo's TECH_STACK.md / CLAUDE.md.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    return conn
