"""M8: FilesystemSource."""

import asyncio
import contextlib
from pathlib import Path

import pytest

from waken import Event, Response, Runtime, target_fn
from waken.plugins.sources.filesystem import FilesystemSource


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


async def _run_watching(
    source: FilesystemSource, runtime: Runtime, seconds: float
) -> None:
    await source.start(runtime)
    await asyncio.sleep(seconds)
    await source.stop()


async def test_new_file_dispatches_exactly_one_event(tmp_path: Path) -> None:
    watch_dir = tmp_path / "inbox"
    received: list[Event] = []

    @target_fn
    async def echo(event: Event) -> Response:
        received.append(event)
        return Response()

    runtime = Runtime()
    runtime.target("echo", echo)
    source = FilesystemSource(watch_dir, target="echo", interval=0.02)

    await source.start(runtime)
    (watch_dir / "new.txt").write_text("hello")
    await asyncio.sleep(0.15)  # let the poll notice it and the dispatch task run
    await source.stop()

    assert len(received) == 1
    assert received[0].payload["path"] == str(watch_dir / "new.txt")
    assert received[0].source == "filesystem"


async def test_preexisting_file_does_not_fire(tmp_path: Path) -> None:
    watch_dir = tmp_path / "inbox"
    watch_dir.mkdir()
    (watch_dir / "already-here.txt").write_text("old news")
    received: list[Event] = []

    @target_fn
    async def echo(event: Event) -> Response:
        received.append(event)
        return Response()

    runtime = Runtime()
    runtime.target("echo", echo)
    source = FilesystemSource(watch_dir, target="echo", interval=0.02)

    await _run_watching(source, runtime, 0.1)

    assert received == []


async def test_session_is_keyed_by_file_path(tmp_path: Path) -> None:
    watch_dir = tmp_path / "inbox"
    received: list[Event] = []

    @target_fn
    async def echo(event: Event) -> Response:
        received.append(event)
        return Response()

    runtime = Runtime()
    runtime.target("echo", echo)
    source = FilesystemSource(watch_dir, target="echo", interval=0.02)

    await source.start(runtime)
    path = watch_dir / "session.txt"
    path.write_text("x")
    await asyncio.sleep(0.15)
    await source.stop()

    assert len(received) == 1
    expected_session_id = runtime.session("filesystem", str(path))
    assert received[0].session_id == expected_session_id


async def test_stop_cancels_the_poll_loop_cleanly(tmp_path: Path) -> None:
    runtime = Runtime()
    source = FilesystemSource(tmp_path / "inbox", target="echo", interval=0.02)

    await source.start(runtime)
    await source.stop()

    with contextlib.suppress(asyncio.CancelledError):
        assert source._task is not None
        assert source._task.done()
