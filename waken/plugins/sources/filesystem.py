"""The built-in `FilesystemSource`.

See docs/api-spec.md §3 (Registration) and §4 (Sessions).
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from waken.events import Event

if TYPE_CHECKING:
    from waken.runtime import Runtime


class FilesystemSource:
    """Dispatches one `Event` per new file appearing under `watch`.

    Polls on `interval` seconds rather than using an OS-level file-watching
    library — this milestone's whole point is adding zero new dependencies
    (see docs/implementation-plan.md, M8). Files already present when
    `start()` runs are the baseline, not new arrivals, and never fire.
    """

    def __init__(
        self, watch: str | Path, target: str, *, interval: float = 1.0
    ) -> None:
        self.watch = Path(watch)
        self.target = target
        self.interval = interval
        self._seen: set[Path] = set()
        self._task: asyncio.Task[None] | None = None

    async def start(self, runtime: Runtime) -> None:
        self.watch.mkdir(parents=True, exist_ok=True)
        self._seen = set(self.watch.iterdir())
        self._task = asyncio.create_task(self._poll(runtime))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _poll(self, runtime: Runtime) -> None:
        while True:
            await asyncio.sleep(self.interval)
            current = set(self.watch.iterdir())
            for path in sorted(current - self._seen):
                event = Event(
                    source="filesystem",
                    target=self.target,
                    payload={"path": str(path)},
                    session_id=runtime.session("filesystem", str(path)),
                )
                # Fire-and-forget, same reasoning as WebhookSource: a slow
                # retry-with-backoff sequence for one file must not stall
                # the loop noticing the next one.
                asyncio.create_task(runtime.dispatch(event, retry=True))
            self._seen = current
