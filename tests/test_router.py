"""M6: the backoff calculation, tested as a pure function."""

import pytest

from waken.router import BACKOFF_FACTOR, BASE_BACKOFF_SECONDS, MAX_BACKOFF_SECONDS
from waken.router import compute_backoff_seconds as backoff


def test_first_retry_uses_base_delay() -> None:
    assert backoff(1) == BASE_BACKOFF_SECONDS


def test_delay_grows_by_backoff_factor_each_attempt() -> None:
    assert backoff(2) == BASE_BACKOFF_SECONDS * BACKOFF_FACTOR
    assert backoff(3) == BASE_BACKOFF_SECONDS * BACKOFF_FACTOR**2


def test_delay_is_capped() -> None:
    assert backoff(20) == MAX_BACKOFF_SECONDS


def test_attempt_below_one_is_invalid() -> None:
    with pytest.raises(ValueError, match="attempt must be >= 1"):
        backoff(0)
