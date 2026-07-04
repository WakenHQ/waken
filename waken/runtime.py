"""The `Runtime` class.

See docs/api-spec.md §3.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import signal
from collections.abc import Callable, Coroutine
from dataclasses import asdict
from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from typing import Any

from waken import router
from waken.events import Event
from waken.exceptions import OutputNotFoundError, TargetNotFoundError, WakenError
from waken.persistence import Database
from waken.plugins.outputs.terminal import TerminalOutput
from waken.plugins.sources.http import HTTPSource
from waken.protocols import Output, Source, Target
from waken.responses import Response
from waken.scheduler import Handler, Scheduler

WebhookHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
Subscriber = Target | Callable[[Any], Any]


class Runtime:
    """Wires Sources, Targets, and Outputs together and routes Events."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = Database(db_path)
        self._targets: dict[str, Target] = {}
        self._outputs: dict[str, Output] = {"terminal": TerminalOutput()}
        self._scheduler = Scheduler(self._db)
        self._sources: dict[str, Source] = {
            "scheduler": self._scheduler,
            "http": HTTPSource(),
        }
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._webhook_handlers: dict[str, WebhookHandler] = {}

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

    async def broadcast(self, *, prompt: str, **payload: Any) -> dict[str, Response]:
        """Send `prompt` to every registered target concurrently.

        A target that raises is captured as a `Response` with the exception
        on `metadata["error"]`, not raised — one bad target never takes down
        a broadcast to the others. Raises `WakenError` if no targets are
        registered at all (the one case this method does raise).
        """
        if not self._targets:
            raise WakenError("broadcast() has no registered targets")

        async def call(name: str) -> tuple[str, Response]:
            event = Event(
                source="api", target=name, payload={"prompt": prompt, **payload}
            )
            try:
                response = await self.dispatch(event)
            except Exception as error:
                response = Response(metadata={"error": str(error)})
            return name, response

        results = await asyncio.gather(*(call(name) for name in self._targets))
        return dict(results)

    def on(self, event_name: str, subscriber: Subscriber) -> None:
        """Subscribe `subscriber` to `event_name` (see `emit()`)."""
        self._subscribers.setdefault(event_name, []).append(subscriber)

    async def emit(self, event_name: str, payload: Any) -> None:
        """Notify every subscriber of `event_name` with `payload`.

        No `Response` is expected and no `Output` is invoked — this is for
        fire-and-forget fan-out, not routing. A `Target` subscriber receives
        an `Event(source="internal", ...)`; a plain callable receives the
        raw `payload` directly.
        """
        for subscriber in self._subscribers.get(event_name, []):
            if isinstance(subscriber, Target):
                normalized_payload = (
                    payload if isinstance(payload, dict) else {"payload": payload}
                )
                event = Event(
                    source="internal", target=event_name, payload=normalized_payload
                )
                await subscriber.handle(event)
            else:
                result = subscriber(payload)
                if isawaitable(result):
                    await result

    def inspect(self) -> dict[str, Any]:
        """A snapshot of registered targets/sources/outputs and queue/job counts."""
        return {
            "targets": sorted(self._targets),
            "sources": sorted(self._sources),
            "outputs": sorted(self._outputs),
            "jobs": self._db.count_jobs(),
            "queue": {
                "pending": self._db.count_queue_entries(status="pending"),
                "dead": self._db.count_queue_entries(status="dead"),
            },
        }

    def serve(
        self, host: str = "127.0.0.1", port: int = 8080, blocking: bool = True
    ) -> asyncio.Task[None] | None:
        """Bind the HTTP source to `host`/`port`, then `run()`.

        Sugar for the common case of choosing a bind address — not a second
        server. Plain `run()` is already reachable over HTTP on the default
        address, since `HTTPSource` is registered by default. `blocking=False`
        returns the `asyncio.Task` and hands control of the event loop back
        to the caller.
        """
        self._sources["http"] = HTTPSource(host, port)
        if blocking:
            self.run()
            return None
        return asyncio.get_event_loop().create_task(self._run_async())

    def run(self) -> None:
        """Start every registered `Source` and block until interrupted.

        Synchronous, like Flask's `app.run()` — the natural bottom-of-script
        call. Ctrl-C/SIGTERM stop every Source in reverse registration order
        before this returns.
        """
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        for source in self._sources.values():
            await source.start(self)

        loop = asyncio.get_running_loop()
        current_task = asyncio.current_task()
        registered_signals: list[signal.Signals] = []
        if current_task is not None:
            for sig in (signal.SIGINT, signal.SIGTERM):
                # NotImplementedError: unsupported platform (e.g. Windows).
                # RuntimeError/ValueError: registering signal handlers only
                # works on the main thread of the main interpreter — raised
                # when _run_async() runs on a background thread (embedding
                # scenarios, tests). Either way, cancellation still works
                # via direct task cancellation; only the OS-signal path is
                # unavailable.
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.add_signal_handler(sig, current_task.cancel)
                    registered_signals.append(sig)

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            for sig in registered_signals:
                loop.remove_signal_handler(sig)
            for source in reversed(list(self._sources.values())):
                await source.stop()
            self._db.close()
