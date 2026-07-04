"""Broadcast: send the same prompt to every registered target concurrently.

    waken run examples/broadcast.py
    python examples/broadcast.py       # equivalent — no server needed here

This one finishes and exits; it's not a long-running `runtime.run()` script.
"""

import asyncio

from waken import Event, Response, Runtime, target_fn


@target_fn
async def shout(event: Event) -> Response:
    return Response(text=event.payload["prompt"].upper())


@target_fn
async def whisper(event: Event) -> Response:
    return Response(text=event.payload["prompt"].lower())


async def main() -> None:
    runtime = Runtime()
    runtime.target("shout", shout)
    runtime.target("whisper", whisper)

    responses = await runtime.broadcast(prompt="Review this architecture.")
    for name, response in responses.items():
        print(f"{name}: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
