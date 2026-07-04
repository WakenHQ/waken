"""The built-in `TerminalOutput`.

See docs/api-spec.md §6 (Writing an Output) and §9 (Error handling).
"""

from __future__ import annotations

from waken.events import Event
from waken.responses import Response


class TerminalOutput:
    """Writes a `Response` to stdout."""

    async def deliver(self, event: Event, response: Response) -> None:
        if response.text is not None:
            print(response.text)
        if response.files:
            print(f"(files: {', '.join(response.files)})")
