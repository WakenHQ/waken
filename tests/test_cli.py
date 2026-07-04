"""M7: the real CLI, as an HTTP client against a real running server.

Per the implementation plan, these deliberately do NOT mock the HTTP layer —
the CLI's entire job is being an HTTP client, so the test runs a real
Runtime, with a real bound socket, on a background thread.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from waken import Event, Response, Runtime, target_fn
from waken.cli import _base_url, main
from waken.plugins.sources.http import HTTPSource


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _RunningServer:
    """A Runtime's HTTP surface, served on a background thread."""

    def __init__(self, runtime: Runtime, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._runtime = runtime
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._runtime.source("http", HTTPSource(self.host, self.port))
        self._task = self._loop.create_task(self._runtime._run_async())
        self._loop.run_until_complete(self._task)

    def start(self) -> None:
        self._thread.start()
        url = f"http://{self.host}:{self.port}/inspect"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                httpx.get(url, timeout=0.2)
                return
            except httpx.TransportError:
                time.sleep(0.02)
        raise RuntimeError("test server did not start in time")

    def stop(self) -> None:
        if self._loop is not None and self._task is not None:
            self._loop.call_soon_threadsafe(self._task.cancel)
        self._thread.join(timeout=2)


@pytest.fixture
def server() -> Iterator[_RunningServer]:
    @target_fn
    async def echo(event: Event) -> Response:
        return Response(text=event.payload["prompt"])

    runtime = Runtime()
    runtime.target("echo", echo)

    running = _RunningServer(runtime, "127.0.0.1", _free_port())
    running.start()
    try:
        yield running
    finally:
        running.stop()


def test_send_wait_prints_response_text(server: _RunningServer) -> None:
    result = CliRunner().invoke(
        main,
        [
            "send",
            "echo",
            "hi",
            "--wait",
            "--host",
            server.host,
            "--port",
            str(server.port),
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "hi"


def test_send_without_wait_prints_nothing(server: _RunningServer) -> None:
    result = CliRunner().invoke(
        main, ["send", "echo", "hi", "--host", server.host, "--port", str(server.port)]
    )

    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_send_to_unknown_target_exits_nonzero(server: _RunningServer) -> None:
    result = CliRunner().invoke(
        main,
        [
            "send",
            "nonexistent",
            "hi",
            "--host",
            server.host,
            "--port",
            str(server.port),
        ],
    )

    assert result.exit_code != 0
    assert "nonexistent" in result.output


def test_inspect_reports_registered_names(server: _RunningServer) -> None:
    result = CliRunner().invoke(
        main, ["inspect", "--host", server.host, "--port", str(server.port)]
    )

    assert result.exit_code == 0
    assert "echo" in result.output
    assert "jobs:" in result.output


def test_inspect_json(server: _RunningServer) -> None:
    result = CliRunner().invoke(
        main,
        ["inspect", "--json", "--host", server.host, "--port", str(server.port)],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "echo" in data["targets"]


def test_emit_reaches_the_server(server: _RunningServer) -> None:
    result = CliRunner().invoke(
        main,
        [
            "emit",
            "invoice.created",
            '{"id": 1}',
            "--host",
            server.host,
            "--port",
            str(server.port),
        ],
    )

    assert result.exit_code == 0


def test_send_with_no_server_running_gives_a_clean_error() -> None:
    result = CliRunner().invoke(
        main,
        ["send", "echo", "hi", "--host", "127.0.0.1", "--port", str(_free_port())],
    )

    assert result.exit_code != 0
    assert "could not reach" in result.output


def test_run_command_executes_the_script_as_main(tmp_path: Path) -> None:
    script = tmp_path / "script.py"
    script.write_text("print(f'hello from {__name__}')\n")

    result = CliRunner().invoke(main, ["run", str(script)])

    assert result.exit_code == 0
    assert "hello from __main__" in result.output


def test_base_url_prefers_explicit_host_and_port() -> None:
    assert _base_url("example.com", 9999) == "http://example.com:9999"
    assert _base_url("example.com", None) == "http://example.com:8080"
    assert _base_url(None, 9999) == "http://127.0.0.1:9999"


def test_base_url_falls_back_to_waken_url_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAKEN_URL", "http://example.com:7777")
    assert _base_url(None, None) == "http://example.com:7777"


def test_base_url_falls_back_to_localhost_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WAKEN_URL", raising=False)
    assert _base_url(None, None) == "http://localhost:8080"
