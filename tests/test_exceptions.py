"""M1: exception hierarchy."""

from waken import OutputNotFoundError, TargetNotFoundError, WakenError


def test_target_not_found_error_carries_name_and_message() -> None:
    error = TargetNotFoundError("claude")
    assert error.name == "claude"
    assert "claude" in str(error)
    assert isinstance(error, WakenError)


def test_output_not_found_error_carries_name_and_message() -> None:
    error = OutputNotFoundError("slack")
    assert error.name == "slack"
    assert "slack" in str(error)
    assert isinstance(error, WakenError)
