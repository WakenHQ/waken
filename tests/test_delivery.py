"""M4: dispatch() delivery resolution."""

from pathlib import Path

import pytest

from waken import Event, OutputNotFoundError, Response, Runtime, target_fn


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


class _RecordingOutput:
    def __init__(self) -> None:
        self.calls: list[tuple[Event, Response]] = []

    async def deliver(self, event: Event, response: Response) -> None:
        self.calls.append((event, response))


def make_runtime() -> Runtime:
    runtime = Runtime()
    runtime.target("echo", echo)
    return runtime


async def test_dispatch_delivers_via_output_matching_event_source() -> None:
    runtime = make_runtime()
    spy = _RecordingOutput()
    runtime.output("terminal", spy)  # overrides the default TerminalOutput

    event = Event(source="terminal", target="echo", payload={"prompt": "hi"})
    response = await runtime.dispatch(event)

    assert len(spy.calls) == 1
    delivered_event, delivered_response = spy.calls[0]
    assert delivered_event == event
    assert delivered_response is response
    assert delivered_response.text == "hi"


async def test_dispatch_skips_delivery_silently_when_source_has_no_output() -> None:
    runtime = make_runtime()
    event = Event(source="unregistered-source", target="echo", payload={"prompt": "hi"})

    response = await runtime.dispatch(event)

    assert response.text == "hi"


async def test_dispatch_raises_output_not_found_for_explicit_missing_output() -> None:
    runtime = make_runtime()
    event = Event(
        source="unregistered-source",
        target="echo",
        payload={"prompt": "hi"},
        output="nonexistent",
    )

    with pytest.raises(OutputNotFoundError) as excinfo:
        await runtime.dispatch(event)

    assert excinfo.value.name == "nonexistent"


async def test_event_output_override_takes_precedence_over_source() -> None:
    runtime = make_runtime()
    spy = _RecordingOutput()
    runtime.output("special", spy)

    # source has no registered output at all; output= should still deliver.
    event = Event(
        source="unregistered-source",
        target="echo",
        payload={"prompt": "hi"},
        output="special",
    )
    await runtime.dispatch(event)

    assert len(spy.calls) == 1


async def test_full_loop_target_and_output_together() -> None:
    runtime = make_runtime()
    spy = _RecordingOutput()
    runtime.output("cli", spy)

    event = Event(source="cli", target="echo", payload={"prompt": "hello"})
    response = await runtime.dispatch(event)

    assert response.text == "hello"
    assert spy.calls == [(event, response)]
