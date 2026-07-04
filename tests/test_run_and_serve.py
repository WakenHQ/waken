"""M10 coverage: Runtime.run() and Runtime.serve(), exercised for real.

M5-M9 only ever exercised the private `_run_async()` core directly; neither
the public sync `run()` nor `serve()` had a test of their own.
"""

import asyncio
import contextlib
import os
import signal
import threading
from pathlib import Path

import pytest

from waken import Runtime
from waken.plugins.sources.http import HTTPSource


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


class _NullSource:
    """A no-op Source, so these tests never bind a real socket."""

    async def start(self, runtime: Runtime) -> None:
        pass

    async def stop(self) -> None:
        pass


def test_serve_blocking_registers_http_source_and_calls_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = Runtime()
    calls: list[str] = []
    monkeypatch.setattr(runtime, "run", lambda: calls.append("ran"))

    result = runtime.serve(host="0.0.0.0", port=9999, blocking=True)

    assert result is None
    assert calls == ["ran"]
    http_source = runtime._sources["http"]
    assert isinstance(http_source, HTTPSource)
    assert http_source.host == "0.0.0.0"
    assert http_source.port == 9999


async def test_serve_non_blocking_returns_a_task() -> None:
    runtime = Runtime()
    runtime.source("http", _NullSource())  # avoid a real bind in this test

    task = runtime.serve(host="127.0.0.1", port=9999, blocking=False)

    assert isinstance(task, asyncio.Task)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def test_run_stops_cleanly_on_sigterm() -> None:
    """The real, public, synchronous entry point — via a real OS signal."""
    runtime = Runtime()
    runtime.source("http", _NullSource())  # avoid a real bind in this test

    timer = threading.Timer(0.1, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    try:
        runtime.run()  # blocks until the signal handler cancels it, then returns
    finally:
        timer.join()
