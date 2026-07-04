"""The `Runtime` class.

See docs/api-spec.md §3.
"""

from __future__ import annotations

import asyncio
from typing import Any

from waken.events import Event
from waken.exceptions import TargetNotFoundError
from waken.protocols import Output, Source, Target
from waken.responses import Response


class Runtime:
    """Wires Sources, Targets, and Outputs together and routes Events."""

    def __init__(self, db_path: str | None = None) -> None:
        # Persistence is wired in M3; accepted now so this signature doesn't
        # change later, but nothing reads `_db_path` yet.
        self._db_path = db_path
        self._targets: dict[str, Target] = {}
        self._sources: dict[str, Source] = {}
        self._outputs: dict[str, Output] = {}

    def target(self, name: str, target: Target) -> None:
        """Register a `Target` under `name`."""
        self._targets[name] = target

    def source(self, name: str, source: Source) -> None:
        """Register a `Source` under `name`."""
        self._sources[name] = source

    def output(self, name: str, output: Output) -> None:
        """Register an `Output` under `name`."""
        self._outputs[name] = output

    async def dispatch(self, event: Event, *, retry: bool = False) -> Response:
        """Route `event` to its registered `Target` and return the `Response`.

        Raises `TargetNotFoundError` if `event.target` isn't registered.
        `retry` is accepted now so the signature is stable, but is a no-op
        until M6 adds the retry/dead-letter queue — a `Target.handle()`
        failure always propagates immediately at this milestone.
        """
        target = self._targets.get(event.target)
        if target is None:
            raise TargetNotFoundError(event.target)
        return await target.handle(event)

    async def send(self, *, target: str, prompt: str, **payload: Any) -> Response:
        """Build an `Event(source="api", ...)` from a plain prompt and dispatch it."""
        event = Event(
            source="api", target=target, payload={"prompt": prompt, **payload}
        )
        return await self.dispatch(event)

    def send_sync(self, *, target: str, prompt: str, **payload: Any) -> Response:
        """Synchronous wrapper over `send()`.

        Raises `RuntimeError` if called from inside a running event loop —
        callers already inside asyncio should await `send()` directly rather
        than risk a silent deadlock.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "send_sync() cannot be called from a running event loop; "
                "await send() instead"
            )
        return asyncio.run(self.send(target=target, prompt=prompt, **payload))
