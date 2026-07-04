"""The Quickstart from docs/api-spec.md.

Runs against a trivial local `echo` target instead of a real LLM adapter, so
it works with no API keys.

    waken run examples/quickstart.py       # in one terminal
    waken send echo "Build tic tac toe." --wait   # in another
"""

from waken import Event, Response, Runtime, target_fn


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


runtime = Runtime()
runtime.target("echo", echo)
runtime.run()
