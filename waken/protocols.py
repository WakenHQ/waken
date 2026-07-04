"""The `Target`, `Source`, and `Output` protocols.

See docs/api-spec.md §2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from waken.events import Event
from waken.responses import Response

if TYPE_CHECKING:
    from waken.runtime import Runtime


@runtime_checkable
class Target(Protocol):
    """Receives an Event, returns a Response. Targets must be interchangeable."""

    async def handle(self, event: Event) -> Response: ...


@runtime_checkable
class Source(Protocol):
    """Produces Events.

    Handed the Runtime at `start()` and calls `await runtime.dispatch(event)`
    whenever external work arrives. Owns its own listening loop (a socket, a
    poll timer, a subprocess) between `start()` and `stop()`.
    """

    async def start(self, runtime: Runtime) -> None: ...

    async def stop(self) -> None: ...


@runtime_checkable
class Output(Protocol):
    """Delivers a Response back through a channel."""

    async def deliver(self, event: Event, response: Response) -> None: ...
