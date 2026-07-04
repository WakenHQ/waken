"""M1: Source/Output structural conformance."""

from waken import Event, Output, Response, Source


class _FakeSource:
    async def start(self, runtime: object) -> None:
        pass

    async def stop(self) -> None:
        pass


class _FakeOutput:
    async def deliver(self, event: Event, response: Response) -> None:
        pass


class _NotASource:
    pass


def test_object_with_start_and_stop_satisfies_source_protocol() -> None:
    assert isinstance(_FakeSource(), Source)


def test_object_with_deliver_satisfies_output_protocol() -> None:
    assert isinstance(_FakeOutput(), Output)


def test_unrelated_object_does_not_satisfy_source_protocol() -> None:
    assert not isinstance(_NotASource(), Source)
