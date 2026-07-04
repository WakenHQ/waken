"""The `Runtime` class.

See docs/api-spec.md §3.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from waken import router
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

        `retry=False` (the default; used by `send()`/`send_sync()` and the
        HTTP `/send/{target}` route): a `Target.handle()` failure propagates
        immediately.

        `retry=True` (used by Sources with no synchronous caller waiting,
        e.g. `WebhookSource`/`FilesystemSource`): a failure is persisted to
        the `queue` table and retried with exponential backoff — base 1s,
        factor 2, capped at 5 minutes — up to 3 attempts, then marked `dead`
        and re-raised. See docs/api-spec.md §9.

        After a successful `Response`, delivery is resolved: an *explicit*
        `event.output` that isn't registered raises `OutputNotFoundError`;
        an *implicit* lookup by `event.source` that isn't registered is
        skipped silently.
        """
        target = self._targets.get(event.target)
        if target is None:
            raise TargetNotFoundError(event.target)

        if not retry:
            response = await target.handle(event)
            await self._deliver(event, response)
            return response

        return await self._dispatch_with_retry(event, target)

    async def _dispatch_with_retry(self, event: Event, target: Target) -> Response:
        event_json = json.dumps(asdict(event))
        attempt = 1
        while True:
            try:
                response = await target.handle(event)
            except Exception:
                if attempt >= router.MAX_ATTEMPTS:
                    self._db.upsert_queue_entry(
                        event_id=event.event_id,
                        event_json=event_json,
                        attempt=attempt,
                        next_attempt_at=datetime.now(UTC),
                        status="dead",
                    )
                    raise
                delay = router.compute_backoff_seconds(attempt)
                self._db.upsert_queue_entry(
                    event_id=event.event_id,
                    event_json=event_json,
                    attempt=attempt,
                    next_attempt_at=datetime.now(UTC),
                    status="pending",
                )
                await asyncio.sleep(delay)
                attempt += 1
            else:
                self._db.remove_queue_entry(event.event_id)
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
