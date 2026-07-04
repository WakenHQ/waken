"""M1: Response."""

from waken import Response


def test_response_defaults() -> None:
    response = Response()
    assert response.text is None
    assert response.files == []
    assert response.data == {}
    assert response.metadata == {}


def test_response_mutable_defaults_are_independent_per_instance() -> None:
    a = Response()
    b = Response()

    a.files.append("game.py")
    a.data["k"] = "v"
    a.metadata["k"] = "v"

    assert b.files == []
    assert b.data == {}
    assert b.metadata == {}


def test_response_with_values() -> None:
    response = Response(text="Done.", files=["game.py"])
    assert response.text == "Done."
    assert response.files == ["game.py"]
