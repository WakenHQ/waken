"""The `Event` type.

See docs/api-spec.md §2.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    """A unit of work traveling from a Source to a Target.

    Frozen: once created, an Event doesn't change as it moves through the
    runtime. Anything a Target needs to add on the way out belongs on the
    Response, not mutated back onto the Event.
    """

    source: str
    target: str
    payload: dict[str, Any]
    session_id: str | None = None
    event_id: str = field(default_factory=lambda: uuid4().hex)
    output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
