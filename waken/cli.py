"""The `waken` CLI.

See docs/api-spec.md §8. Every command except `run` is an HTTP client
against a running `Runtime` (started via `run()` or `serve()`) — the same
relationship the `docker` CLI has to `dockerd`.
"""

from __future__ import annotations

import json
import os
import runpy

import click
import httpx


def _base_url(host: str | None, port: int | None) -> str:
    if host or port:
        return f"http://{host or '127.0.0.1'}:{port or 8080}"
    return os.environ.get("WAKEN_URL", "http://localhost:8080")


def _request(method: str, url: str, **kwargs: object) -> httpx.Response:
    try:
        return httpx.request(method, url, timeout=10.0, **kwargs)  # type: ignore[arg-type]
    except httpx.ConnectError as error:
        raise click.ClickException(
            f"could not reach a running Waken instance at {url} ({error})"
        ) from error


@click.group()
def main() -> None:
    """Waken: route work from a Source to an interchangeable Target to an Output."""


@main.command("run")
@click.argument("script", type=click.Path(exists=True))
def run_command(script: str) -> None:
    """Execute SCRIPT, which is expected to build a Runtime and call run()."""
    runpy.run_path(script, run_name="__main__")


@main.command("send")
@click.argument("target")
@click.argument("prompt")
@click.option("--wait", is_flag=True, help="Print the Response text.")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def send_command(
    target: str, prompt: str, wait: bool, host: str | None, port: int | None
) -> None:
    """POST /send/TARGET with PROMPT."""
    url = f"{_base_url(host, port)}/send/{target}"
    response = _request("POST", url, json={"prompt": prompt})
    if response.status_code >= 400:
        raise click.ClickException(response.json().get("error", response.text))
    if wait:
        click.echo(response.json().get("text") or "")


@main.command("emit")
@click.argument("event")
@click.argument("payload")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def emit_command(event: str, payload: str, host: str | None, port: int | None) -> None:
    """POST /emit/EVENT with PAYLOAD (a JSON string)."""
    url = f"{_base_url(host, port)}/emit/{event}"
    _request("POST", url, json=json.loads(payload))


@main.command("inspect")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def inspect_command(as_json: bool, host: str | None, port: int | None) -> None:
    """GET /inspect: registered targets/sources/outputs, jobs, and queue depth."""
    url = f"{_base_url(host, port)}/inspect"
    data = _request("GET", url).json()
    if as_json:
        click.echo(json.dumps(data))
        return
    click.echo(f"targets: {', '.join(data['targets']) or '(none)'}")
    click.echo(f"sources: {', '.join(data['sources']) or '(none)'}")
    click.echo(f"outputs: {', '.join(data['outputs']) or '(none)'}")
    click.echo(f"jobs:    {data['jobs']}")
    click.echo(
        f"queue:   {data['queue']['pending']} pending, {data['queue']['dead']} dead"
    )
