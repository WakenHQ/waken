"""M6: dispatch(event, retry=True) retry/dead-letter behavior."""

import asyncio
from pathlib import Path

import pytest

from waken import Event, Response, Runtime, target_fn


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _instant_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff delays would otherwise cost real seconds in these tests."""

    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant_sleep)


async def test_always_failing_target_is_dead_lettered_after_three_attempts() -> None:
    attempts: list[int] = []

    @target_fn
    async def boom(event: Event) -> Response:
        attempts.append(1)
        raise ValueError("nope")

    runtime = Runtime()
    runtime.target("boom", boom)
    event = Event(source="webhook", target="boom", payload={})

    with pytest.raises(ValueError, match="nope"):
        await runtime.dispatch(event, retry=True)

    assert len(attempts) == 3

    (dead,) = runtime._db.dead_letters()
    assert dead.event_id == event.event_id
    assert dead.status == "dead"
    assert dead.attempt == 3


async def test_target_failing_twice_then_succeeding_delivers_and_clears_queue() -> None:
    attempts: list[int] = []

    @target_fn
    async def flaky(event: Event) -> Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("not yet")
        return Response(text="finally")

    runtime = Runtime()
    runtime.target("flaky", flaky)
    event = Event(source="webhook", target="flaky", payload={})

    response = await runtime.dispatch(event, retry=True)

    assert len(attempts) == 3
    assert response.text == "finally"
    assert runtime._db.dead_letters() == []

    (row,) = runtime._db._connection.execute(
        "SELECT COUNT(*) AS n FROM queue WHERE event_id = ?", (event.event_id,)
    ).fetchall()
    assert row["n"] == 0


async def test_send_still_raises_immediately_without_retry() -> None:
    """M2 regression: send()/dispatch(retry=False) must not change."""

    @target_fn
    async def boom(event: Event) -> Response:
        raise ValueError("target failure")

    runtime = Runtime()
    runtime.target("boom", boom)

    with pytest.raises(ValueError, match="target failure"):
        await runtime.send(target="boom", prompt="hi")

    assert runtime._db.dead_letters() == []


async def test_dead_letters_query_function() -> None:
    runtime = Runtime()

    @target_fn
    async def boom(event: Event) -> Response:
        raise RuntimeError("always fails")

    runtime.target("boom", boom)
    event = Event(source="webhook", target="boom", payload={"x": 1})

    with pytest.raises(RuntimeError):
        await runtime.dispatch(event, retry=True)

    (entry,) = runtime._db.dead_letters()
    assert entry.event_id == event.event_id
    assert '"x": 1' in entry.event_json
