"""Webhook: turn an inbound HTTP POST into a routed Event.

    waken run examples/webhook.py   # in one terminal

    curl -X POST http://localhost:8080/webhook/github \\
         -H 'Content-Type: application/json' \\
         -d '{"issue": {"title": "Bug: it crashes"}}'

Watch the terminal for the routed prompt.
"""

from typing import Any

from waken import Event, Response, Runtime, target_fn
from waken.plugins.sources.webhook import WebhookSource


@target_fn
async def echo(event: Event) -> Response:
    print(event.payload["prompt"])
    return Response(text=event.payload["prompt"])


def parse_github_issue(body: dict[str, Any]) -> Event:
    title = body.get("issue", {}).get("title", "(no title)")
    return Event(
        source="webhook", target="echo", payload={"prompt": f"New issue: {title}"}
    )


runtime = Runtime()
runtime.target("echo", echo)
runtime.source("github", WebhookSource("github", parse_github_issue))
runtime.run()
