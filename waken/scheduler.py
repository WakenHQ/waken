"""The `Scheduler` built-in Source backing `every`/`after`/`at`/`cron`.

See docs/api-spec.md §3.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from croniter import croniter

from waken.persistence import Database, Job

if TYPE_CHECKING:
    from waken.runtime import Runtime

Handler = Callable[[], Awaitable[Any]]

_RECURRING_KINDS = ("every", "cron")


def job_id_for(func: Handler) -> str:
    """The stable id a job is keyed by: `f"{module}:{qualname}"`."""
    return f"{func.__module__}:{func.__qualname__}"


class Scheduler:
    """Fires registered handlers on a schedule, persisted to the `jobs` table."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._handlers: dict[str, Handler] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def every(self, func: Handler, **kwargs: float) -> None:
        job_id = job_id_for(func)
        self._handlers[job_id] = func
        self._db.ensure_job(
            job_id=job_id,
            kind="every",
            spec=json.dumps(kwargs),
            target_module=func.__module__,
            target_qualname=func.__qualname__,
            default_next_fire_at=datetime.now(UTC) + timedelta(**kwargs),
        )

    def after(self, func: Handler, **kwargs: float) -> None:
        job_id = job_id_for(func)
        self._handlers[job_id] = func
        self._db.ensure_job(
            job_id=job_id,
            kind="after",
            spec=json.dumps(kwargs),
            target_module=func.__module__,
            target_qualname=func.__qualname__,
            default_next_fire_at=datetime.now(UTC) + timedelta(**kwargs),
        )

    def at(self, func: Handler, when: str) -> None:
        job_id = job_id_for(func)
        self._handlers[job_id] = func
        moment = datetime.fromisoformat(when)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        self._db.ensure_job(
            job_id=job_id,
            kind="at",
            spec=json.dumps({"when": when}),
            target_module=func.__module__,
            target_qualname=func.__qualname__,
            default_next_fire_at=moment,
        )

    def cron(self, func: Handler, expression: str) -> None:
        job_id = job_id_for(func)
        self._handlers[job_id] = func
        self._db.ensure_job(
            job_id=job_id,
            kind="cron",
            spec=json.dumps({"expression": expression}),
            target_module=func.__module__,
            target_qualname=func.__qualname__,
            default_next_fire_at=_next_cron_fire(expression, datetime.now(UTC)),
        )

    async def start(self, runtime: Runtime) -> None:
        for job in self._db.pending_jobs():
            handler = self._handlers.get(job.job_id)
            if handler is None:
                # Not re-registered by this process; nothing to call yet.
                continue
            self._schedule(job, handler)

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _schedule(self, job: Job, handler: Handler) -> None:
        self._tasks[job.job_id] = asyncio.create_task(self._fire_when_due(job, handler))

    async def _fire_when_due(self, job: Job, handler: Handler) -> None:
        delay = max(0.0, (job.next_fire_at - datetime.now(UTC)).total_seconds())
        await asyncio.sleep(delay)
        await handler()

        if job.kind in _RECURRING_KINDS:
            next_fire_at = _compute_next_fire_at(job)
            self._db.update_job_next_fire_at(job.job_id, next_fire_at)
            self._schedule(
                Job(
                    job_id=job.job_id,
                    kind=job.kind,
                    spec=job.spec,
                    target_module=job.target_module,
                    target_qualname=job.target_qualname,
                    next_fire_at=next_fire_at,
                    created_at=job.created_at,
                ),
                handler,
            )
        else:
            self._db.delete_job(job.job_id)
            self._tasks.pop(job.job_id, None)


def _compute_next_fire_at(job: Job) -> datetime:
    spec = json.loads(job.spec)
    if job.kind == "every":
        return datetime.now(UTC) + timedelta(**spec)
    if job.kind == "cron":
        return _next_cron_fire(spec["expression"], datetime.now(UTC))
    raise ValueError(f"{job.kind!r} jobs do not recur")


def _next_cron_fire(expression: str, start: datetime) -> datetime:
    result = croniter(expression, start).get_next(datetime)
    return result if result.tzinfo is not None else result.replace(tzinfo=UTC)
