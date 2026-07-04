"""The `target_fn` decorator.

See docs/api-spec.md §2 (`Target`).
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable

from waken.events import Event
from waken.protocols import Target
from waken.responses import Response

Handler = Callable[[Event], Awaitable[Response]]


class _FunctionTarget:
    """Adapts a plain async function to the `Target` protocol."""

    def __init__(self, func: Handler) -> None:
        self._func = func
        for attr in functools.WRAPPER_ASSIGNMENTS:
            value = getattr(func, attr, None)
            if value is not None:
                setattr(self, attr, value)
        self.__wrapped__ = func

    async def handle(self, event: Event) -> Response:
        return await self._func(event)


def target_fn(func: Handler) -> Target:
    """Wrap a plain `async def handler(event: Event) -> Response` as a `Target`.

    ```python
    @target_fn
    async def echo(event: Event) -> Response:
        return Response(text=event.payload["prompt"])

    runtime.target("echo", echo)
    ```
    """
    return _FunctionTarget(func)
