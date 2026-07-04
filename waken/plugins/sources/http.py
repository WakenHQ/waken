"""The built-in `HTTPSource`.

See docs/api-spec.md §3 (HTTP).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Generator
from typing import TYPE_CHECKING

import uvicorn

from waken.server import create_app

if TYPE_CHECKING:
    from waken.runtime import Runtime


class _SignalSafeServer(uvicorn.Server):
    """A `uvicorn.Server` that never touches process signal handlers.

    `Runtime.run()` owns SIGINT/SIGTERM handling; letting uvicorn install its
    own `signal.signal()` handlers underneath it would silently steal them.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


class HTTPSource:
    """Serves the ASGI app from `waken.server.create_app` via uvicorn."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        self.host = host
        self.port = port
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self, runtime: Runtime) -> None:
        app = create_app(runtime)
        config = uvicorn.Config(
            app, host=self.host, port=self.port, log_level="warning"
        )
        self._server = _SignalSafeServer(config)
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
