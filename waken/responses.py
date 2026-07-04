"""The `Response` type.

See docs/api-spec.md §2.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Response:
    """What a Target returns after handling an Event.

    `data` is for structured results a custom Output might want (e.g. a
    Slack Output rendering blocks); most Targets only ever set `text` and
    `files`.
    """

    text: str | None = None
    files: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
