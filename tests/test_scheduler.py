"""M5: every/after/at/cron decorators and restart persistence."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from waken import Runtime
from waken.scheduler import _next_cron_fire


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


class _NullSource:
    """Replaces the default HTTPSource so scheduler tests don't bind a real port."""

    async def start(self, runtime: Runtime) -> None:
        pass

    async def stop(self) -> None:
        pass


async def run_briefly(runtime: Runtime, seconds: float) -> None:
    """Run the runtime for a short window, then cancel and clean up.

    `Runtime.run()` is a synchronous, blocking `asyncio.run()` wrapper (see
    docs/api-spec.md §3) and so can't itself be awaited from inside a
    running test loop; `_run_async()` is the awaitable core it wraps.

    These tests only care about the Scheduler, so the default HTTPSource
    (which would otherwise try to bind a real socket on every call) is
    swapped for a no-op stub.
    """
    runtime.source("http", _NullSource())
    task = asyncio.create_task(runtime._run_async())
    await asyncio.sleep(seconds)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_every_fires_repeatedly() -> None:
    calls: list[int] = []

    runtime = Runtime()

    @runtime.every(seconds=0.02)
    async def tick() -> None:
        calls.append(1)

    await run_briefly(runtime, 0.11)

    assert len(calls) >= 2


async def test_after_fires_exactly_once() -> None:
    calls: list[int] = []

    runtime = Runtime()

    @runtime.after(seconds=0.02)
    async def once() -> None:
        calls.append(1)

    # Run for much longer than the interval; a bug that treats "after" like
    # "every" would fire this several times.
    await run_briefly(runtime, 0.1)

    assert len(calls) == 1


async def test_at_in_the_past_fires_immediately_on_start() -> None:
    calls: list[int] = []
    when = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    runtime = Runtime()

    @runtime.at(when)
    async def once() -> None:
        calls.append(1)

    await run_briefly(runtime, 0.02)

    assert calls == [1]


async def test_at_in_the_future_does_not_fire_early() -> None:
    calls: list[int] = []
    when = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()

    runtime = Runtime()

    @runtime.at(when)
    async def once() -> None:
        calls.append(1)

    await run_briefly(runtime, 0.02)

    assert calls == []


async def test_at_in_the_future_fires_when_due() -> None:
    calls: list[int] = []
    when = (datetime.now(UTC) + timedelta(seconds=0.03)).isoformat()

    runtime = Runtime()

    @runtime.at(when)
    async def once() -> None:
        calls.append(1)

    await run_briefly(runtime, 0.08)

    assert calls == [1]


def test_cron_computes_correct_next_fire_time() -> None:
    start = datetime(2026, 7, 4, 8, 0, tzinfo=UTC)

    next_fire = _next_cron_fire("0 9 * * *", start)
    assert next_fire == datetime(2026, 7, 4, 9, 0, tzinfo=UTC)

    next_fire_after = _next_cron_fire("0 9 * * *", next_fire)
    assert next_fire_after == datetime(2026, 7, 5, 9, 0, tzinfo=UTC)


def test_cron_decorator_persists_job_with_computed_next_fire(tmp_path: Path) -> None:
    runtime = Runtime(db_path=tmp_path / "cron.db")

    @runtime.cron("0 9 * * *")
    async def daily_report() -> None:
        pass

    (job,) = runtime._db.pending_jobs()
    assert job.kind == "cron"
    assert job.next_fire_at.hour == 9


async def test_every_job_survives_restart(tmp_path: Path) -> None:
    """The schedule persists in the jobs table, not just in memory."""
    db_path = tmp_path / "shared.db"
    calls: list[int] = []

    async def tick() -> None:
        calls.append(1)

    runtime1 = Runtime(db_path=db_path)
    runtime1.every(seconds=0.01)(tick)

    # runtime1.run() is never called — the job has not fired yet, only its
    # schedule (next_fire_at) has been written to the jobs table.
    await asyncio.sleep(0.05)  # let next_fire_at fall into the past

    # A brand new Runtime/Scheduler/Database, pointed at the same file.
    runtime2 = Runtime(db_path=db_path)
    runtime2.every(seconds=0.01)(tick)  # re-register the same function

    await run_briefly(runtime2, 0.05)

    assert calls, "job should have fired on runtime2 using the persisted schedule"


async def test_job_not_reregistered_in_this_process_is_not_fired() -> None:
    """A job with no matching in-memory handler is skipped, not crashed on."""
    db_path_holder = Runtime()

    @db_path_holder.every(seconds=1000)
    async def never_called() -> None:
        raise AssertionError("should not run")

    # A fresh Runtime never re-decorates `never_called`, so its handler map
    # is empty for that job_id — start() must skip it, not raise.
    fresh = Runtime(db_path=db_path_holder._db.path)
    await run_briefly(fresh, 0.02)
