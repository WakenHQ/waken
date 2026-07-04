"""Scheduling: every/after/at/cron are all sugar over the built-in Scheduler.

    waken run examples/scheduler.py

Watch the terminal — "tick" prints every 2 seconds, "hello" once after 5.
"""

from waken import Event, Response, Runtime, target_fn


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


runtime = Runtime()
runtime.target("echo", echo)


@runtime.every(seconds=2)
async def tick() -> None:
    response = await runtime.send(target="echo", prompt="tick")
    print(response.text)


@runtime.after(seconds=5)
async def greet_once() -> None:
    response = await runtime.send(target="echo", prompt="hello, five seconds later")
    print(response.text)


runtime.run()
