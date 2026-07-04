"""M7 (moved forward from M9): runtime.emit()/runtime.on()."""

from pathlib import Path

import pytest

from waken import Event, Response, Runtime, target_fn


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


async def test_emit_invokes_a_target_subscriber_with_a_synthesized_event() -> None:
    received: list[Event] = []

    @target_fn
    async def accounting(event: Event) -> Response:
        received.append(event)
        return Response(text="recorded")

    runtime = Runtime()
    runtime.on("invoice.created", accounting)

    await runtime.emit("invoice.created", {"id": 1})

    assert len(received) == 1
    assert received[0].source == "internal"
    assert received[0].target == "invoice.created"
    assert received[0].payload == {"id": 1}


async def test_emit_invokes_a_plain_callable_with_raw_payload() -> None:
    logged: list[object] = []

    def log(invoice: object) -> None:
        logged.append(invoice)

    runtime = Runtime()
    runtime.on("invoice.created", log)

    invoice = {"id": 1, "amount": 42}
    await runtime.emit("invoice.created", invoice)

    assert logged == [invoice]


async def test_emit_invokes_an_async_plain_callable() -> None:
    logged: list[object] = []

    async def log(invoice: object) -> None:
        logged.append(invoice)

    runtime = Runtime()
    runtime.on("invoice.created", log)

    await runtime.emit("invoice.created", {"id": 1})

    assert logged == [{"id": 1}]


async def test_emit_notifies_multiple_subscribers() -> None:
    calls: list[str] = []

    runtime = Runtime()
    runtime.on("x", lambda _: calls.append("first"))
    runtime.on("x", lambda _: calls.append("second"))

    await runtime.emit("x", {})

    assert calls == ["first", "second"]


async def test_emit_with_no_subscribers_does_nothing() -> None:
    runtime = Runtime()
    await runtime.emit("nobody-listening", {"whatever": True})


async def test_emit_does_not_attempt_output_delivery() -> None:
    from waken.plugins.outputs.terminal import TerminalOutput

    delivered: list[tuple[Event, Response]] = []

    class _RecordingOutput(TerminalOutput):
        async def deliver(self, event: Event, response: Response) -> None:
            delivered.append((event, response))

    @target_fn
    async def accounting(event: Event) -> Response:
        return Response(text="recorded")

    runtime = Runtime()
    runtime.output("internal", _RecordingOutput())
    runtime.on("invoice.created", accounting)

    await runtime.emit("invoice.created", {"id": 1})

    assert delivered == []


async def test_emit_wraps_non_dict_payload_for_target_subscribers() -> None:
    received: list[Event] = []

    @target_fn
    async def accounting(event: Event) -> Response:
        received.append(event)
        return Response()

    class Invoice:
        pass

    invoice = Invoice()
    runtime = Runtime()
    runtime.on("invoice.created", accounting)

    await runtime.emit("invoice.created", invoice)

    assert received[0].payload == {"payload": invoice}
