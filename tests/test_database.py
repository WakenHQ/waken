"""M3: the `Database` wrapper directly."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from waken.persistence import SCHEMA_VERSION, Database


def test_migrate_sets_schema_version(tmp_path: Path) -> None:
    db = Database(tmp_path / "waken.db")
    (version,) = db._connection.execute("PRAGMA user_version").fetchone()
    assert version == SCHEMA_VERSION


def test_reopening_existing_database_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "waken.db"

    first = Database(db_path)
    session_id = first.get_or_create_session("slack", "T1")

    second = Database(db_path)
    assert second.get_or_create_session("slack", "T1") == session_id


def test_parent_directory_is_created(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "waken.db"
    Database(db_path)
    assert db_path.exists()


def test_close_closes_the_underlying_connection(tmp_path: Path) -> None:
    db = Database(tmp_path / "waken.db")
    db.close()

    with pytest.raises(sqlite3.ProgrammingError):
        db._connection.execute("SELECT 1")


def test_count_queue_entries_with_no_status_filter_counts_everything(
    tmp_path: Path,
) -> None:
    db = Database(tmp_path / "waken.db")
    db.upsert_queue_entry(
        event_id="a",
        event_json=json.dumps({}),
        attempt=1,
        next_attempt_at=datetime.now(UTC),
        status="pending",
    )
    db.upsert_queue_entry(
        event_id="b",
        event_json=json.dumps({}),
        attempt=3,
        next_attempt_at=datetime.now(UTC),
        status="dead",
    )

    assert db.count_queue_entries() == 2
    assert db.count_queue_entries(status="pending") == 1
    assert db.count_queue_entries(status="dead") == 1
