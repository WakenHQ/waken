"""SQLite-backed `Database` wrapper (sessions, jobs, queue tables).

See docs/adr/0001-core-architecture.md.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 2

DEFAULT_DB_PATH = Path(".waken/waken.db")


@dataclass(frozen=True, slots=True)
class Job:
    """One row of the `jobs` table."""

    job_id: str
    kind: str
    spec: str
    target_module: str
    target_qualname: str
    next_fire_at: datetime
    created_at: datetime


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
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    spec TEXT NOT NULL,
                    target_module TEXT NOT NULL,
                    target_qualname TEXT NOT NULL,
                    next_fire_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
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

    def ensure_job(
        self,
        *,
        job_id: str,
        kind: str,
        spec: str,
        target_module: str,
        target_qualname: str,
        default_next_fire_at: datetime,
    ) -> None:
        """Insert a `jobs` row for `job_id` only if one doesn't already exist.

        A pre-existing row (e.g. after a process restart re-applies the same
        decorator) is left untouched — its `next_fire_at` is the schedule's
        source of truth, not whatever the fresh decorator call would compute.
        """
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            "INSERT OR IGNORE INTO jobs "
            "(job_id, kind, spec, target_module, target_qualname, "
            "next_fire_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                kind,
                spec,
                target_module,
                target_qualname,
                default_next_fire_at.isoformat(),
                now,
            ),
        )
        self._connection.commit()

    def pending_jobs(self) -> list[Job]:
        """All rows currently in the `jobs` table."""
        rows = self._connection.execute(
            "SELECT job_id, kind, spec, target_module, target_qualname, "
            "next_fire_at, created_at FROM jobs"
        ).fetchall()
        return [
            Job(
                job_id=row["job_id"],
                kind=row["kind"],
                spec=row["spec"],
                target_module=row["target_module"],
                target_qualname=row["target_qualname"],
                next_fire_at=datetime.fromisoformat(row["next_fire_at"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def update_job_next_fire_at(self, job_id: str, next_fire_at: datetime) -> None:
        self._connection.execute(
            "UPDATE jobs SET next_fire_at = ? WHERE job_id = ?",
            (next_fire_at.isoformat(), job_id),
        )
        self._connection.commit()

    def delete_job(self, job_id: str) -> None:
        self._connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        self._connection.commit()
