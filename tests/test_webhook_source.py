"""M8: WebhookSource."""

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from waken import Event, Response, Runtime, target_fn
from waken.plugins.sources.webhook import WebhookSource
from waken.server import create_app


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _parser(body: dict[str, Any]) -> Event:
    return Event(source="webhook", target="echo", payload={"prompt": body["text"]})


async def _start_webhook_source(runtime: Runtime) -> None:
    source = WebhookSource("github", _parser)
    runtime.source("github-webhook", source)
    await source.start(runtime)


def test_registered_webhook_dispatches_the_parsed_event() -> None:
    received: list[Event] = []

    @target_fn
    async def echo(event: Event) -> Response:
        received.append(event)
        return Response(text=event.payload["prompt"])

    runtime = Runtime()
    runtime.target("echo", echo)
    asyncio.run(_start_webhook_source(runtime))

    client = TestClient(create_app(runtime))
    result = client.post("/webhook/github", json={"text": "hello"})

    assert result.status_code == 200
    assert result.json() == {"ok": True}

    # Dispatch is fire-and-forget (see server.py) — the route already
    # returned by the time it runs, so give the background task a moment.
    for _ in range(50):
        if received:
            break
        time.sleep(0.02)

    assert len(received) == 1
    assert received[0].payload["prompt"] == "hello"


def test_unregistered_webhook_name_returns_404() -> None:
    runtime = Runtime()
    client = TestClient(create_app(runtime))

    result = client.post("/webhook/nonexistent", json={})

    assert result.status_code == 404
    assert "nonexistent" in result.json()["error"]


async def test_stop_removes_the_handler() -> None:
    runtime = Runtime()
    source = WebhookSource("github", _parser)
    await source.start(runtime)
    assert "github" in runtime._webhook_handlers

    await source.stop()

    assert "github" not in runtime._webhook_handlers
