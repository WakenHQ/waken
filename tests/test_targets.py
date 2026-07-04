"""M1: target_fn and structural Target conformance."""

from waken import Event, Response, Target, target_fn


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


def test_target_fn_wrapped_function_satisfies_target_protocol() -> None:
    assert isinstance(echo, Target)


async def test_target_fn_wrapped_function_is_callable_via_handle() -> None:
    event = Event(source="cli", target="echo", payload={"prompt": "hi"})
    response = await echo.handle(event)
    assert response.text == "hi"


def test_target_fn_preserves_function_identity() -> None:
    assert echo.__name__ == "echo"
