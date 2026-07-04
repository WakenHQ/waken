"""M8: NotificationOutput."""

import logging

import pytest

from waken import Event, Response
from waken.plugins.outputs.notification import NotificationOutput


async def test_degrades_to_a_warning_when_unsupported(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No notify-send/osascript on this platform (true in this CI sandbox)."""
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr("platform.system", lambda: "Linux")

    output = NotificationOutput()
    event = Event(source="scheduler", target="echo", payload={})

    with caplog.at_level(logging.WARNING):
        await output.deliver(event, Response(text="hello"))

    assert any("skipping" in record.message for record in caplog.records)


async def test_uses_notify_send_when_available_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")

    def which(name: str) -> str | None:
        return "/usr/bin/notify-send" if name == "notify-send" else None

    monkeypatch.setattr("shutil.which", which)

    calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*args: str) -> None:
        calls.append(args)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    output = NotificationOutput(title="Waken")
    event = Event(source="scheduler", target="echo", payload={})
    await output.deliver(event, Response(text="hello"))

    assert calls == [("notify-send", "Waken", "hello")]


async def test_uses_osascript_when_available_on_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    def which(name: str) -> str | None:
        return "/usr/bin/osascript" if name == "osascript" else None

    monkeypatch.setattr("shutil.which", which)

    calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*args: str) -> None:
        calls.append(args)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    output = NotificationOutput(title="Waken")
    event = Event(source="scheduler", target="echo", payload={})
    await output.deliver(event, Response(text="hello"))

    assert calls[0][0] == "osascript"
    assert "hello" in calls[0][2]


async def test_real_environment_has_no_notifier_and_degrades_gracefully(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No mocking: confirms the real degrade path in this sandbox (no desktop)."""
    output = NotificationOutput()
    event = Event(source="scheduler", target="echo", payload={})

    with caplog.at_level(logging.WARNING):
        await output.deliver(event, Response(text="hello"))

    assert any("skipping" in record.message for record in caplog.records)
