"""SQLite-backed `Database` wrapper (sessions, jobs, queue tables).

See docs/adr/0001-core-architecture.md.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1

DEFAULT_DB_PATH = Path(".waken/waken.db")


class Database:
    """Owns the SQLite connection and schema for one `Runtime`.

    Zero-config: the file and its parent directory are created on first use,
    and the schema is created (or brought up to date) via a single
    `PRAGMA user_version`-gated migration step run once at construction.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        (version,) = self._connection.execute("PRAGMA user_version").fetchone()
        if version < SCHEMA_VERSION:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    source TEXT NOT NULL,
                    external_key TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (source, external_key)
                )
                """
            )
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def get_or_create_session(self, source: str, external_key: str) -> str:
        """Mint-or-return the `session_id` for `(source, external_key)`."""
        now = datetime.now(UTC).isoformat()

        row = self._connection.execute(
            "SELECT session_id FROM sessions WHERE source = ? AND external_key = ?",
            (source, external_key),
        ).fetchone()
        if row is not None:
            self._connection.execute(
                "UPDATE sessions SET last_seen_at = ? "
                "WHERE source = ? AND external_key = ?",
                (now, source, external_key),
            )
            self._connection.commit()
            return str(row["session_id"])

        session_id = uuid4().hex
        self._connection.execute(
            "INSERT INTO sessions "
            "(source, external_key, session_id, created_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (source, external_key, session_id, now, now),
        )
        self._connection.commit()
        return session_id
