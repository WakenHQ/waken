# ADR 0001: Waken Core Architecture

- **Status:** Proposed
- **Date:** 2026-07-04
- **Related:** [Prior Art Review](../prior-art.md), [Public API Specification](../api-spec.md)

## Problem Statement

Getting an AI agent to answer work that arrives from an arbitrary place — a
Slack message, a voice command, a GitHub webhook, a cron tick, an HTTP
request — and deliver the answer back through the right channel, is currently
solved by hand, once per (source, target, output) triple, in every project that
needs it. [Prior Art Review](../prior-art.md) shows this precisely: agent
frameworks orchestrate *within* a run someone else already started; "agent
gateways" govern what an agent calls *outward*; MCP and A2A standardize
agent→tool and agent→agent. Nobody standardizes *what wakes the agent, and
where the answer goes*. Every partial solution found is either vendor-locked
(Claude Code Channels, Gemini CLI, Copilot Agent HQ), the wrong installation
weight class (Airflow/Celery/Temporal/NATS all require a broker or database
before message #1), or scoped well beyond what a router needs to be (memory,
skills, multi-agent orchestration).

Waken is a small runtime that fills exactly that gap and nothing else: receive
work, route it to the correct agent, return the response through the
appropriate channel.

## Decision

### Two packages, one direction of dependency

```
waken/            core: router, scheduler, persistence, event bus, HTTP, CLI
waken-<adapter>/  optional: waken-claude, waken-gemini, waken-copilot, ...
```

`waken` never imports an adapter package. Adapters depend on `waken` (for the
`Target` protocol and the `Event`/`Response` types) and register themselves by
name. This is the same shape as `requests` + `requests-oauthlib`, or Flask +
Flask extensions: the core has no idea `waken-claude` exists at import time.

### Five types, and nothing else at the center

```python
Event(source, target, payload, session_id, event_id, metadata)
Response(text, files, data, metadata)
Source    # produces Events
Target    # receives an Event, returns a Response  ("must be interchangeable")
Output    # delivers a Response back through a channel
```

`Runtime` is the object that wires these together. It does three things:

1. **Registration** — `runtime.source(...)`, `runtime.target(...)`,
   `runtime.output(...)` — a name-keyed registry for each of the three
   protocols, so any of them can be swapped without touching the other two.
2. **Routing** — `runtime.dispatch(event)`: look up `event.target` in the
   target registry, call it, get a `Response` back. This is the entire
   "engine." There is no planner, no graph, no DAG evaluator — a lookup and a
   call.
3. **Delivery** — after dispatch, look up an `Output` (default: the output
   registered under the same name as `event.source`; overridable per-event) and
   call `output.deliver(event, response)`. HTTP is the degenerate case: the
   "output" is just returning the response body to the still-open request, so
   `HTTPSource` implements delivery itself rather than routing through the
   `Output` registry.

Everything else in the core — scheduling, persistence, retries, the HTTP
server, the CLI — exists to make steps 1–3 reliable and configuration-free, not
to add a fourth thing the runtime does.

### Async core, sync-friendly edges

`Target.handle()`, `Output.deliver()`, and `Runtime.dispatch()` are `async def`.
Talking to an LLM is I/O-bound and often concurrent (a webhook burst, a
scheduled job firing while a Slack message is mid-flight); asyncio is the only
sane default. `Runtime.send()` gets a `run_sync()`-style synchronous wrapper
(same trick as the OpenAI Agents SDK and `httpx`) so `waken send claude "hi"`
and quick scripts don't force `asyncio.run()` on every caller.

### Sessions: the runtime tracks the *pointer*, adapters own the *history*

A `Session` is a `(source, external_conversation_key) -> session_id` mapping,
persisted in SQLite. The runtime mints and looks up `session_id` and attaches
it to every `Event`; it never inspects or stores conversation content. A
`ClaudeAdapter` is free to keep a transcript however it wants — SDK session
objects, a file, its own database — keyed by that `session_id`. This mirrors
the split that MCP's own 2026 spec revision converged on independently (opaque
handles instead of protocol-level session affinity) and that the OpenAI Agents
SDK, LangGraph, and MAF all arrived at by different routes: the router and the
conversation-state owner should never be the same piece of code, because they
change for different reasons and at different speeds.

### Persistence: one SQLite file, autocreated, no migrations framework

Three tables, created on first run if absent:

| table | purpose |
|---|---|
| `sessions` | `(source, external_key) -> session_id` |
| `jobs` | scheduled jobs (`every`/`after`/`at`/`cron`), next-fire time, payload |
| `queue` | events pending delivery or retry, with attempt count and backoff |

No ORM, no Alembic. Schema changes ship as an `ALTER TABLE`-or-recreate step run
once at `Runtime()` construction, gated by a `PRAGMA user_version`. This is
deliberately primitive: the moment persistence needs more than three tables and
a version pragma, that's a signal the runtime is trying to do more than route,
schedule, and retry — which is the line this project draws on purpose.

### Plugins are the *only* extension mechanism

Sources, Targets, and Outputs are all the same shape: a small protocol plus a
name. There is no separate "plugin system" API distinct from
`runtime.source/target/output`. Built-in Sources/Outputs (CLI, HTTP,
filesystem, webhook / terminal, notifications) live in `waken.plugins.*` and
are registered the same way a user's own would be — the core does not
special-case them. This is the test for whether the plugin system is minimal
enough: if the built-ins need a private API the public plugin author can't
reach, the design has failed.

`Scheduler` (`waken.scheduler.Scheduler`) is the one exception, and lives at
the top level alongside `router.py`/`persistence.py` rather than under
`waken.plugins.sources`: it's not a swappable third-party integration the way
Filesystem or Webhook are, it's the thing `runtime.every/after/at/cron` are
sugar over, and it shares the `jobs` table with the rest of core persistence.
It still satisfies the plain `Source` protocol and is registered through the
same `runtime.source()` call as everything else — the exception is about
which directory the file lives in, not about a second registration
mechanism.

### HTTP server and CLI are thin wrappers, not new surfaces

The HTTP source (built on Starlette, the same minimal ASGI toolkit FastAPI
itself is built on — not FastAPI, to avoid pulling in Pydantic as a hard
dependency for a three-route server) is registered by default, exposing:

```
POST /send/{target}
POST /emit/{event}
POST /webhook/{name}
```

`runtime.run()` alone is therefore already reachable over HTTP.
`runtime.serve(host, port)` is sugar for picking a non-default bind address —
it re-registers the HTTP source with that address and calls `run()` — not a
second server. The CLI (`waken`) talks to *any* running `Runtime` (via `run()`
or `serve()`) over that same HTTP surface for `send`/`inspect` — the same
relationship `docker` CLI has to `dockerd`, or `celery` CLI has to a running
worker. `waken run app.py` is the one CLI command that doesn't need a server
already running: it imports and executes the user's script, which is expected
to construct a `Runtime` and call `run()` (or `serve()`) itself. There is no
separate, persistent "CLI source" — the CLI is purely an HTTP client.

## Alternatives Considered

**Sync-only core (no asyncio).** Simpler mental model, matches Flask/Requests
exactly. Rejected: the moment two Sources fire concurrently (a scheduled job and
an inbound webhook), a sync core needs threads anyway, and Target adapters
calling LLM APIs are naturally async today (every major SDK surveyed —
Anthropic, OpenAI, Google — ships an async client as the primary interface).
Async-first with a sync convenience wrapper gets both without a threading model
bolted on later.

**A generic event-bus core (Runtime is just pub/sub; routing is a subscriber
pattern).** Considered because `runtime.emit`/`runtime.on` already look like
pub/sub, and it would unify "route to a target" and "notify subscribers" into
one mechanism. Rejected as the *primary* model: pub/sub has no natural place for
"exactly one Target answers, and I need its Response back to deliver
somewhere" — the core case — without bolting reply-topics or correlation IDs
onto every event, which is exactly the complexity NATS/Redis Streams needed to
add request-reply semantics on top of raw pub/sub. Kept as a *secondary*
capability (`emit`/`on`) for the many-listeners case that genuinely is
fire-and-forget (e.g., `invoice.created` fanning out to several interested
handlers with no Response expected).

**Config-file-driven routing (declare sources/targets/routes in YAML/TOML, no
Python).** Considered because it would let non-Python users wire up routing.
Rejected for v1: the brief's own priority order puts "beautiful API" above
"extensibility," and a config-file DSL is a second API surface to keep
elegant and versioned. Nothing prevents a thin YAML-to-`Runtime()` loader from
being built as a separate, optional layer later once the Python API has proven
itself — but the DSL should not be designed before the API it would wrap.

**Everything-is-an-adapter-package, including built-in Sources/Outputs (CLI,
HTTP, scheduler ship as `waken-cli`, `waken-http`, etc.).** Considered for
architectural purity — "Core must never depend on adapters" taken to its
logical extreme. Rejected: CLI, HTTP, and scheduler are not optional the way a
Claude or Gemini adapter is optional — a router that can't be reached by HTTP or
run from a terminal isn't a router yet. The line is drawn at *Target* adapters
(which encode a paid vendor's API and SDK, and which genuinely have zero
business being a hard dependency of the core) — not at every plugin.

## Rejected Alternatives (broader shape)

- **Build on an existing workflow engine (Airflow/Temporal) and add a thin
  routing layer on top.** Rejected outright: every one of these requires a
  server/broker/database before the first message moves, which is the exact
  installation weight this project exists to avoid. Confirmed in the Prior Art
  Review — this isn't a guess, both projects' own 2026 AI integrations still
  require their full server stack.
- **Standardize on MCP as the transport instead of inventing `Event`/
  `Response`.** Rejected: MCP is host-initiated (an agent reaching for tools) and
  is mid-way through removing session/state machinery in its 2026-07-28
  revision precisely because it doesn't fit this direction of traffic. Building
  Waken's core envelope *on* MCP would import a protocol solving the opposite
  problem. Waken may expose an MCP-shaped Source/Target adapter later (letting
  an MCP host trigger a route, or a route call into MCP tools) — but the core
  wire format stays Waken's own, small `Event`/`Response`.
- **Ship a hosted/managed version first (SaaS), library second.** Rejected as
  the starting point: every closed competitor in the Prior Art Review
  (Anthropic, Google, Microsoft, GitHub) is already racing to ship exactly this
  as a hosted product. The opening is the small, self-hostable, vendor-neutral
  library nobody big has an incentive to ship — that has to exist before any
  hosted layer would even make sense.

## Tradeoffs

| Choice | We gain | We give up |
|---|---|---|
| SQLite-only persistence | Zero-config, zero-ops, works offline, trivially inspectable with any SQLite tool | Horizontal scaling across multiple processes/machines without an external lock; acceptable because this project's target deployment is "one process, one machine," not a distributed job queue |
| Asyncio core | Natural concurrency for I/O-bound LLM calls, matches every major provider SDK | A sync-only shop must wrap calls (`asyncio.run`/the provided sync helper); mitigated by shipping the sync wrapper as first-class, not an afterthought |
| No built-in memory/RAG/vector store | Stays a router, not a framework; adapters own their own state however they like | Users wanting shared cross-target memory must build or bring it themselves; this is intentional — see Non-Goals |
| Adapters are separate packages, not part of core | Core install stays tiny (per the `pip install waken` goal); no vendor SDK is ever a transitive dependency of the router | One extra `pip install waken-claude` per target; judged a fair price for keeping core dependency-free |
| Name-keyed registries instead of a dependency-injection framework | Anyone can read `runtime.target("claude", ClaudeAdapter())` and know exactly what happens | No compile-time checking that a target name used in `Event(target=...)` was actually registered; caught at dispatch time with a clear error, not statically — an acceptable, Flask-like tradeoff (Flask doesn't statically check route names either) |

## Future Evolution

- **Wire-format standardization.** If `Event`/`Response` prove durable, publish
  them as a versioned, documented schema independent of the Python types, so
  non-Python Sources (a Go webhook receiver, a Rust CLI) can produce/consume
  them without depending on this library. ACP and A2A are the reference shapes
  to study first.
- **Multi-process fan-out.** If a single SQLite-backed process becomes a real
  bottleneck for some users, the persistence layer's narrow interface (three
  tables, one pragma-gated migration step) is the seam where a Postgres or
  Redis-backed implementation could be swapped in — without changing
  `Runtime`, `Source`, `Target`, or `Output`. Not built until someone has this
  problem for real.
- **MCP/A2A bridging adapters.** An `MCPTarget` that forwards an `Event` into an
  MCP host's tool-call surface, and an `A2ATarget` that speaks A2A to a remote
  agent, are natural adapters to ship once the core is stable — they compose
  with, rather than replace, the routing model.
- **Declarative routing layer.** A thin YAML/TOML-to-`Runtime` loader, once the
  Python API has enough real usage to know which parts are worth making
  declarative and which aren't.
- **Webhook signature verification.** `WebhookSource`'s `parser` callback (and
  the `POST /webhook/{name}` route in `waken/server.py` that calls it) only
  ever receives the parsed JSON body — no request headers, no raw body bytes.
  This is fine for sources that don't need it, but it blocks any integration
  that authenticates webhooks via an HMAC signature over headers + raw body
  (Slack's classic HTTP Events API, GitHub webhooks, Stripe, and most other
  webhook-signing providers all work this way). Found independently while
  building both `waken-slack` and `waken-telegram`; both sidestepped it by
  using a persistent-connection transport instead (Slack Socket Mode,
  Telegram long polling — see [adapter-ci-setup.md](../adapter-ci-setup.md)),
  which is a reasonable choice for those two providers but isn't available to
  every future webhook-based Source. Fixing this for real means deciding what
  `Parser` receives instead of a bare `dict` — headers alongside the body,
  the raw bytes for HMAC purposes, or a small `WebhookRequest` wrapper type —
  which is a real interface-design decision for `api-spec.md`, not a one-line
  patch, so it isn't done here.
