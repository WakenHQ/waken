"""Target/Output registry lookup and dispatch resolution.

See docs/adr/0001-core-architecture.md.
"""

from __future__ import annotations

BASE_BACKOFF_SECONDS = 1.0
BACKOFF_FACTOR = 2.0
MAX_BACKOFF_SECONDS = 300.0
MAX_ATTEMPTS = 3


def compute_backoff_seconds(attempt: int) -> float:
    """Delay before retry `attempt` (1-indexed).

    `base * factor ** (attempt - 1)`, capped at `MAX_BACKOFF_SECONDS`. See
    docs/api-spec.md §9: base 1s, factor 2, cap 5 minutes.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    delay = BASE_BACKOFF_SECONDS * (BACKOFF_FACTOR ** (attempt - 1))
    return min(delay, MAX_BACKOFF_SECONDS)
