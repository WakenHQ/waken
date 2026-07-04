"""The built-in `NotificationOutput`.

See docs/api-spec.md §6 (Writing an Output).
"""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil

from waken.events import Event
from waken.responses import Response

logger = logging.getLogger(__name__)


class NotificationOutput:
    """Sends a desktop notification for a `Response`'s text.

    Shells out to whatever notification command is already present on the
    platform (`notify-send` on Linux, `osascript` on macOS) rather than
    depending on a Python notification library — this milestone's whole
    point is adding zero new dependencies. Degrades to a logged warning, not
    a crash, when neither command is available (e.g. a headless Linux box
    with no notification daemon, or Windows, which has no equivalent
    zero-dependency system command).
    """

    def __init__(self, title: str = "Waken") -> None:
        self.title = title

    async def deliver(self, event: Event, response: Response) -> None:
        command = self._command(response.text or "")
        if command is None:
            logger.warning(
                "NotificationOutput: no supported notification command found "
                "on this platform (%s); skipping.",
                platform.system(),
            )
            return
        await asyncio.create_subprocess_exec(*command)

    def _command(self, message: str) -> list[str] | None:
        system = platform.system()
        if system == "Linux" and shutil.which("notify-send"):
            return ["notify-send", self.title, message]
        if system == "Darwin" and shutil.which("osascript"):
            script = f"display notification {message!r} with title {self.title!r}"
            return ["osascript", "-e", script]
        return None
