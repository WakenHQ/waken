"""M1: Event."""

from dataclasses import FrozenInstanceError

import pytest

from waken import Event


def test_event_is_frozen() -> None:
    event = Event(source="cli", target="echo", payload={})
    with pytest.raises(FrozenInstanceError):
        event.target = "other"  # type: ignore[misc]


def test_event_id_autogenerates_and_is_unique() -> None:
    a = Event(source="cli", target="echo", payload={})
    b = Event(source="cli", target="echo", payload={})
    assert a.event_id
    assert b.event_id
    assert a.event_id != b.event_id


def test_event_id_can_be_set_explicitly() -> None:
    event = Event(source="cli", target="echo", payload={}, event_id="fixed")
    assert event.event_id == "fixed"


def test_event_defaults() -> None:
    event = Event(source="cli", target="echo", payload={"prompt": "hi"})
    assert event.session_id is None
    assert event.output is None
    assert event.metadata == {}


def test_event_equality_and_repr() -> None:
    a = Event(source="cli", target="echo", payload={"prompt": "hi"}, event_id="x")
    b = Event(source="cli", target="echo", payload={"prompt": "hi"}, event_id="x")
    c = Event(source="cli", target="echo", payload={"prompt": "bye"}, event_id="x")
    assert a == b
    assert a != c
    assert "cli" in repr(a)
    assert "echo" in repr(a)
