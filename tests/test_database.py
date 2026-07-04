"""M3: the `Database` wrapper directly."""

from pathlib import Path

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
