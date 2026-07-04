"""The `Runtime` class.

See docs/api-spec.md §3.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from waken.events import Event
from waken.exceptions import OutputNotFoundError, TargetNotFoundError
from waken.persistence import Database
from waken.plugins.outputs.terminal import TerminalOutput
from waken.protocols import Output, Source, Target
from waken.responses import Response
from waken.scheduler import Handler, Scheduler


class Runtime:
    """Wires Sources, Targets, and Outputs together and routes Events."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = Database(db_path)
        self._targets: dict[str, Target] = {}
        self._outputs: dict[str, Output] = {"terminal": TerminalOutput()}
        self._scheduler = Scheduler(self._db)
        self._sources: dict[str, Source] = {"scheduler": self._scheduler}

    def target(self, name: str, target: Target) -> None:
        """Register a `Target` under `name`."""
        self._targets[name] = target

    def source(self, name: str, source: Source) -> None:
        """Register a `Source` under `name`."""
        self._sources[name] = source

    def output(self, name: str, output: Output) -> None:
        """Register an `Output` under `name`."""
        self._outputs[name] = output

    def session(self, source: str, external_key: str) -> str:
        """Mint-or-return a stable `session_id` for `(source, external_key)`.

        The runtime never reads or stores conversation content — only this
        one mapping, persisted to SQLite. See docs/api-spec.md §4.
        """
        return self._db.get_or_create_session(source, external_key)

    def every(self, **kwargs: float) -> Callable[[Handler], Handler]:
        """Decorate a handler to run repeatedly every `timedelta(**kwargs)`."""

        def decorator(func: Handler) -> Handler:
            self._scheduler.every(func, **kwargs)
            return func

        return decorator

    def after(self, **kwargs: float) -> Callable[[Handler], Handler]:
        """Decorate a handler to run exactly once, `timedelta(**kwargs)` from now."""

        def decorator(func: Handler) -> Handler:
            self._scheduler.after(func, **kwargs)
            return func

        return decorator

    def at(self, when: str) -> Callable[[Handler], Handler]:
        """Decorate a handler to run exactly once at an ISO 8601 timestamp."""

        def decorator(func: Handler) -> Handler:
            self._scheduler.at(func, when)
            return func

        return decorator

    def cron(self, expression: str) -> Callable[[Handler], Handler]:
        """Decorate a handler to run repeatedly on a cron schedule."""

        def decorator(func: Handler) -> Handler:
            self._scheduler.cron(func, expression)
            return func

        return decorator

    async def dispatch(self, event: Event, *, retry: bool = False) -> Response:
        """Route `event` to its registered `Target` and return the `Response`.

        Raises `TargetNotFoundError` if `event.target` isn't registered.
        `retry` is accepted now so the signature is stable, but is a no-op
        until M6 adds the retry/dead-letter queue — a `Target.handle()`
        failure always propagates immediately at this milestone.

        After a successful `Response`, delivery is resolved per docs/api-spec.md
        §9: an *explicit* `event.output` that isn't registered raises
        `OutputNotFoundError`; an *implicit* lookup by `event.source` that
        isn't registered is skipped silently.
        """
        target = self._targets.get(event.target)
        if target is None:
            raise TargetNotFoundError(event.target)
        response = await target.handle(event)
        await self._deliver(event, response)
        return response

    async def _deliver(self, event: Event, response: Response) -> None:
        if event.output is not None:
            output = self._outputs.get(event.output)
            if output is None:
                raise OutputNotFoundError(event.output)
        else:
            output = self._outputs.get(event.source)
            if output is None:
                return
        await output.deliver(event, response)

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

    async def run(self) -> None:
        """Start every registered `Source` and block until cancelled.

        Calls `await source.start(self)` for each registered Source, then
        waits. Cancelling this coroutine (e.g. via task cancellation, or a
        signal handler wired up by the CLI) stops every Source in reverse
        registration order before the cancellation propagates.
        """
        for source in self._sources.values():
            await source.start(self)
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            for source in reversed(list(self._sources.values())):
                await source.stop()
