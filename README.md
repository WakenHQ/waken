<div align="center">

<img src="assets/logo.svg" width="96" height="96" alt="Waken logo">

# Waken

[![CI](https://github.com/waken-dev/waken/actions/workflows/ci.yml/badge.svg)](https://github.com/waken-dev/waken/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2f81f7)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&size=20&pause=1200&color=6E7681&center=true&vCenter=true&width=600&lines=nginx+for+AI+agents;Source+%E2%86%92+Runtime+%E2%86%92+Target+%E2%86%92+Output;small.+elegant.+composable.)](docs/api-spec.md)

</div>

A lightweight runtime that routes work from a Source, to an interchangeable
AI-agent Target, back through an Output.

```
Source → Runtime → Target → Response → Output
```

It is **not** an agent framework, an orchestration engine, a workflow
builder, or an LLM wrapper — those are things you plug into it. Waken's own
job is small on purpose: receive work, route it to the correct agent, return
the result through the right channel. Think "nginx for AI agents," not
"another LangGraph."

## Install

```bash
pip install waken
```

Zero external services — no Docker, no Redis, no Postgres. State (sessions,
scheduled jobs, retry queue) lives in one SQLite file, created automatically.

## Quickstart

```python
# app.py
from waken import Event, Response, Runtime, target_fn


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


runtime = Runtime()
runtime.target("echo", echo)
runtime.run()
```

```bash
waken run app.py
```

In another terminal:

```bash
waken send echo "Build tic tac toe." --wait
# Build tic tac toe.
```

That's it — `runtime.run()` is already reachable over HTTP
(`http://localhost:8080`), with a CLI, a scheduler, and a retry queue on the
same object, no extra setup. A real deployment swaps `echo` for a Target
adapter (`waken-claude`, `waken-gemini`, ...) — same shape, same three lines.

## What it does

- **Sources** turn something happening — an HTTP request, a webhook, a
  scheduled tick, a new file — into an `Event`.
- **Targets** receive an `Event` and return a `Response`. Swapping
  `ClaudeAdapter()` for `GeminiAdapter()` is a one-line change; nothing else
  in the runtime has to know.
- **Outputs** deliver a `Response` back through a channel (terminal, Slack,
  email, ...) — decoupled from wherever the `Event` came from.

```python
runtime.target("claude", ClaudeAdapter())
runtime.target("gemini", GeminiAdapter())

@runtime.every(hours=1)
async def hourly_summary():
    await runtime.send(target="claude", prompt="Summarize today's commits.")

runtime.serve(port=8080)
```

More runnable examples: [`examples/`](examples/) (scheduling, broadcasting to
multiple targets, routing an inbound webhook).

## CLI

```bash
waken run <script.py>          # execute a script that builds a Runtime and calls run()
waken send <target> <prompt>   # POST /send/<target> on a running instance
waken emit <event> <json>      # POST /emit/<event>
waken inspect                  # targets, sources, outputs, jobs, queue depth
```

## Documentation

- [Prior art review](docs/prior-art.md) — what this fills that agent
  frameworks, MCP/A2A, and 2026's wave of "agent gateways" don't.
- [Architecture Decision Record](docs/adr/0001-core-architecture.md) — the
  design and the alternatives it rejected.
- [Public API specification](docs/api-spec.md) — the full API, with examples.
- [Implementation plan](docs/implementation-plan.md) — milestones, and how
  the actual build diverged from the original plan along the way.

## Status

Pre-release. The core API described above is implemented and tested; real
Target adapters (`waken-claude`, `waken-gemini`, `waken-copilot`, ...) ship
as separate packages and haven't been built yet — see the [ADR's
alternatives](docs/adr/0001-core-architecture.md) for why core never depends
on them.

## Development

```bash
git clone https://github.com/waken-dev/waken
cd waken
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE)
