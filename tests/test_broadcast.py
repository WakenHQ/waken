"""M9: runtime.broadcast()."""

from pathlib import Path

import pytest

from waken import Event, Response, Runtime, WakenError, target_fn


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@target_fn
async def shout(event: Event) -> Response:
    return Response(text=event.payload["prompt"].upper())


@target_fn
async def whisper(event: Event) -> Response:
    return Response(text=event.payload["prompt"].lower())


@target_fn
async def boom(event: Event) -> Response:
    raise ValueError("target failure")


async def test_broadcast_sends_to_every_target_concurrently() -> None:
    runtime = Runtime()
    runtime.target("shout", shout)
    runtime.target("whisper", whisper)

    responses = await runtime.broadcast(prompt="Hi")

    assert responses["shout"].text == "HI"
    assert responses["whisper"].text == "hi"


async def test_broadcast_captures_a_failing_target_without_raising() -> None:
    runtime = Runtime()
    runtime.target("shout", shout)
    runtime.target("whisper", whisper)
    runtime.target("boom", boom)

    responses = await runtime.broadcast(prompt="Hi")

    assert len(responses) == 3
    assert responses["shout"].text == "HI"
    assert responses["whisper"].text == "hi"
    assert "target failure" in responses["boom"].metadata["error"]


async def test_broadcast_with_no_targets_raises() -> None:
    runtime = Runtime()

    with pytest.raises(WakenError, match="no registered targets"):
        await runtime.broadcast(prompt="Hi")
