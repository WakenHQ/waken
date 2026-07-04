"""The built-in HTTP source's ASGI app.

See docs/api-spec.md §3 (HTTP).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from waken.events import Event
from waken.exceptions import TargetNotFoundError

if TYPE_CHECKING:
    from waken.runtime import Runtime


def create_app(runtime: Runtime) -> Starlette:
    """Build the ASGI app exposing `/send`, `/emit`, `/webhook`, and `/inspect`."""

    async def send(request: Request) -> JSONResponse:
        target = request.path_params["target"]
        body = await request.json()
        event = Event(
            source="http",
            target=target,
            payload={"prompt": body["prompt"]},
            session_id=body.get("session_id"),
        )
        try:
            response = await runtime.dispatch(event)
        except TargetNotFoundError as error:
            return JSONResponse({"error": str(error)}, status_code=404)
        return JSONResponse(asdict(response))

    async def emit(request: Request) -> JSONResponse:
        event_name = request.path_params["event"]
        payload = await request.json()
        await runtime.emit(event_name, payload)
        return JSONResponse({"ok": True})

    async def webhook(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        handler = runtime._webhook_handlers.get(name)
        if handler is None:
            return JSONResponse(
                {"error": f"no webhook registered as {name!r}"}, status_code=404
            )
        body = await request.json()
        await handler(body)
        return JSONResponse({"ok": True})

    async def inspect(request: Request) -> JSONResponse:
        return JSONResponse(runtime.inspect())

    return Starlette(
        routes=[
            Route("/send/{target}", send, methods=["POST"]),
            Route("/emit/{event}", emit, methods=["POST"]),
            Route("/webhook/{name}", webhook, methods=["POST"]),
            Route("/inspect", inspect, methods=["GET"]),
        ]
    )
