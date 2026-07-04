"""M3: persistence and sessions."""

from pathlib import Path

import pytest

from waken import Runtime


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_session_mints_and_returns_stable_id() -> None:
    runtime = Runtime()
    first = runtime.session("slack", "T1")
    second = runtime.session("slack", "T1")
    assert first == second


def test_session_differs_by_external_key() -> None:
    runtime = Runtime()
    a = runtime.session("slack", "T1")
    b = runtime.session("slack", "T2")
    assert a != b


def test_session_differs_by_source() -> None:
    runtime = Runtime()
    a = runtime.session("slack", "T1")
    b = runtime.session("email", "T1")
    assert a != b


def test_session_persists_across_runtime_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "shared.db"

    first_runtime = Runtime(db_path=db_path)
    session_id = first_runtime.session("slack", "T1")

    second_runtime = Runtime(db_path=db_path)
    assert second_runtime.session("slack", "T1") == session_id


def test_default_db_path_created_under_cwd(tmp_path: Path) -> None:
    Runtime()
    assert (tmp_path / ".waken" / "waken.db").exists()


def test_recreating_db_after_deletion_does_not_crash(tmp_path: Path) -> None:
    db_path = tmp_path / "waken.db"

    runtime = Runtime(db_path=db_path)
    old_session_id = runtime.session("slack", "T1")

    db_path.unlink()

    new_runtime = Runtime(db_path=db_path)
    new_session_id = new_runtime.session("slack", "T1")

    assert new_session_id
    assert new_session_id != old_session_id
