"""The built-in `WebhookSource`.

See docs/api-spec.md §3 (HTTP) and §6 (Writing a Source).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from waken.events import Event

if TYPE_CHECKING:
    from waken.runtime import Runtime

Parser = Callable[[dict[str, Any]], Event]


class WebhookSource:
    """Registers a named route under `POST /webhook/{name}`.

    Served by the built-in HTTPSource (see `waken.server.create_app`); this
    class only supplies the `name` -> handler mapping the route looks up.
    `parser` turns the raw JSON request body into an `Event` to dispatch.
    """

    def __init__(self, name: str, parser: Parser) -> None:
        self.name = name
        self._parser = parser
        self._runtime: Runtime | None = None

    async def start(self, runtime: Runtime) -> None:
        self._runtime = runtime

        async def handle(body: dict[str, Any]) -> None:
            event = self._parser(body)
            await runtime.dispatch(event, retry=True)

        runtime._webhook_handlers[self.name] = handle

    async def stop(self) -> None:
        if self._runtime is not None:
            self._runtime._webhook_handlers.pop(self.name, None)
