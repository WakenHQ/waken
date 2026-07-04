"""Waken's exception hierarchy.

See docs/api-spec.md §9.
"""


class WakenError(Exception):
    """Base class for all errors raised by Waken."""


class TargetNotFoundError(WakenError):
    """Raised when an `Event.target` has no registered `Target`."""

    def __init__(self, name: str) -> None:
        super().__init__(f"no target registered as {name!r}")
        self.name = name


class OutputNotFoundError(WakenError):
    """Raised when an explicit `Event.output` has no registered `Output`."""

    def __init__(self, name: str) -> None:
        super().__init__(f"no output registered as {name!r}")
        self.name = name
