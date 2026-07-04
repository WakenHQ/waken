"""M2: Runtime registration and routing (in-memory).

Since M3, plain `Runtime()` creates `.waken/waken.db` in the CWD by default
(see docs/api-spec.md §3), so every test here runs inside an isolated
temp directory to avoid touching the real developer's filesystem.
"""

import asyncio
from pathlib import Path

import pytest

from waken import Event, Response, Runtime, TargetNotFoundError, target_fn


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


@target_fn
async def shout(event: Event) -> Response:
    return Response(text=event.payload["prompt"].upper())


@target_fn
async def boom(event: Event) -> Response:
    raise ValueError("target failure")


def make_runtime() -> Runtime:
    runtime = Runtime()
    runtime.target("echo", echo)
    runtime.target("shout", shout)
    runtime.target("boom", boom)
    return runtime


async def test_dispatch_routes_to_the_correct_target() -> None:
    runtime = make_runtime()

    echo_event = Event(source="cli", target="echo", payload={"prompt": "hi"})
    shout_event = Event(source="cli", target="shout", payload={"prompt": "hi"})

    assert (await runtime.dispatch(echo_event)).text == "hi"
    assert (await runtime.dispatch(shout_event)).text == "HI"


async def test_dispatch_raises_target_not_found_error() -> None:
    runtime = make_runtime()
    event = Event(source="cli", target="nonexistent", payload={})

    with pytest.raises(TargetNotFoundError) as excinfo:
        await runtime.dispatch(event)

    assert excinfo.value.name == "nonexistent"
    assert "nonexistent" in str(excinfo.value)


async def test_dispatch_propagates_target_failure_by_default() -> None:
    runtime = make_runtime()
    event = Event(source="cli", target="boom", payload={})

    with pytest.raises(ValueError, match="target failure"):
        await runtime.dispatch(event)


async def test_send_builds_event_and_dispatches() -> None:
    runtime = make_runtime()
    response = await runtime.send(target="shout", prompt="hi")
    assert response.text == "HI"


def test_send_sync_works_with_no_running_loop() -> None:
    runtime = make_runtime()
    response = runtime.send_sync(target="echo", prompt="hi")
    assert response.text == "hi"


def test_send_sync_raises_clear_error_inside_running_loop() -> None:
    runtime = make_runtime()

    async def call_from_inside_loop() -> None:
        runtime.send_sync(target="echo", prompt="hi")

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(call_from_inside_loop())


def test_registering_source_and_output_does_not_raise() -> None:
    class _FakeSource:
        async def start(self, runtime: Runtime) -> None:
            pass

        async def stop(self) -> None:
            pass

    class _FakeOutput:
        async def deliver(self, event: Event, response: Response) -> None:
            pass

    runtime = Runtime()
    runtime.source("fake", _FakeSource())
    runtime.output("fake", _FakeOutput())
