"""M7: the HTTP surface, exercised via an in-process ASGI test client (no socket)."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from waken import Event, Response, Runtime, target_fn
from waken.server import create_app


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


def make_client() -> TestClient:
    runtime = Runtime()
    runtime.target("echo", echo)
    return TestClient(create_app(runtime))


def test_send_dispatches_and_returns_response_json() -> None:
    client = make_client()
    result = client.post("/send/echo", json={"prompt": "hi"})

    assert result.status_code == 200
    assert result.json()["text"] == "hi"


def test_send_to_unknown_target_returns_404_with_error() -> None:
    client = make_client()
    result = client.post("/send/nonexistent", json={"prompt": "hi"})

    assert result.status_code == 404
    assert "nonexistent" in result.json()["error"]


def test_emit_returns_ok() -> None:
    client = make_client()
    result = client.post("/emit/invoice.created", json={"id": 1})

    assert result.status_code == 200
    assert result.json() == {"ok": True}


def test_webhook_unregistered_name_returns_404() -> None:
    client = make_client()
    result = client.post("/webhook/github", json={})

    assert result.status_code == 404
    assert "github" in result.json()["error"]


def test_inspect_reflects_registered_names_and_counts() -> None:
    client = make_client()
    data = client.get("/inspect").json()

    assert "echo" in data["targets"]
    assert "terminal" in data["outputs"]
    assert "scheduler" in data["sources"]
    assert "http" in data["sources"]
    assert data["jobs"] == 0
    assert data["queue"] == {"pending": 0, "dead": 0}
