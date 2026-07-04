# Waken Public API Specification

The API is the product. This document specifies it in full, with examples,
before any implementation exists. If implementation later disagrees with this
document, the implementation changes.

```bash
pip install waken
```

---

## 1. Quickstart

```python
from waken import Runtime
from waken_claude import ClaudeAdapter

runtime = Runtime()
runtime.target("claude", ClaudeAdapter())
runtime.run()
```

That's a complete program. `run()` starts every registered `Source` — which by
default includes the built-in HTTP source, so another terminal can reach it —
and routes anything addressed to `"claude"` to `ClaudeAdapter`. Send it
something:

```bash
waken send claude "Build tic tac toe."
```

---

## 2. Core types

### `Event`

```python
from dataclasses import dataclass, field
from uuid import uuid4

@dataclass(frozen=True, slots=True)
class Event:
    source: str
    target: str
    payload: dict
    session_id: str | None = None
    event_id: str = field(default_factory=lambda: uuid4().hex)
    output: str | None = None          # override which Output delivers the Response
    metadata: dict = field(default_factory=dict)
```

```python
Event(
    source="voice",
    target="claude",
    payload={"prompt": "Build me tic tac toe."},
)
```

`Event` is frozen: once created, it doesn't change as it moves through the
runtime. Anything a `Target` needs to add on the way out belongs on the
`Response`, not mutated back onto the `Event`.

### `Response`

```python
from dataclasses import dataclass, field

@dataclass(slots=True)
class Response:
    text: str | None = None
    files: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
```

```python
Response(
    text="Done.",
    files=["game.py"],
)
```

`data` is for structured results a custom `Output` might want (e.g. a Slack
Output rendering blocks); most Targets only ever set `text` and `files`.

### `Target`

```python
from typing import Protocol

class Target(Protocol):
    async def handle(self, event: Event) -> Response: ...
```

The entire adapter contract is one method. Anything implementing it can be
registered as a target — a real LLM adapter, a mock in a test, or a plain
function wrapped by `waken.target_fn`:

```python
from waken import target_fn

@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])

runtime.target("echo", echo)
```

### `Source`

```python
class Source(Protocol):
    async def start(self, runtime: "Runtime") -> None: ...
    async def stop(self) -> None: ...
```

A `Source` is handed the `Runtime` at `start()` and calls
`await runtime.dispatch(event)` whenever external work arrives. It owns its own
listening loop (a socket, a poll timer, a subprocess) between `start()` and
`stop()`. There is no separate "CLI source" that runs inside `Runtime.run()` —
the CLI is a client of the HTTP source (see [§8](#8-cli)), not a listener
alongside it.

### `Output`

```python
class Output(Protocol):
    async def deliver(self, event: Event, response: Response) -> None: ...
```

Called after dispatch, with both the original `Event` (so the `Output` knows
where the work came from) and the resulting `Response`.

---

## 3. `Runtime`

```python
from waken import Runtime

runtime = Runtime(db_path=".waken/waken.db")   # default path shown; auto-created
```

### Registration

```python
runtime.target("claude", ClaudeAdapter())
runtime.target("gemini", GeminiAdapter())
runtime.target("copilot", CopilotAdapter())

runtime.source("http", HTTPSource())            # built-in, also added by default
runtime.source("filesystem", FilesystemSource(watch="./inbox"))

runtime.output("slack", SlackOutput(token=...))  # from waken_slack, a separate package
runtime.output("terminal", TerminalOutput())    # built-in, also added by default
```

Targets, Sources, and Outputs are interchangeable by construction: nothing else
in the runtime cares which concrete class is behind the name. Swapping
`"claude"` from `ClaudeAdapter()` to `GeminiAdapter()` requires changing exactly
one line.

### Sending work directly

```python
response = await runtime.send(target="claude", prompt="Build tic tac toe.")
```

```python
response = runtime.send_sync(target="claude", prompt="Build tic tac toe.")
```

`send`/`send_sync` build an `Event(source="api", target=..., payload={"prompt":
...})` for you — the common case of "I just want to talk to one target" doesn't
require constructing an `Event` by hand. For anything beyond a plain prompt
string, build the `Event` yourself and call `runtime.dispatch(event)`.

### `dispatch()`

```python
async def dispatch(self, event: Event, *, retry: bool = False) -> Response: ...
```

This is the one method every `Source` and every `send`/`broadcast` call
ultimately goes through, and it has two independent knobs worth being explicit
about (see [§9](#9-error-handling) for the full contract):

- **Failure handling** is controlled by `retry`. `send()`/`send_sync()` and the
  HTTP `/send/{target}` route all call `dispatch(event, retry=False)` — there's
  a caller on the other end waiting synchronously, so a `Target` failure
  surfaces as an immediate exception (or HTTP 5xx), not a multi-minute retry
  loop. Sources with no synchronous caller (`Scheduler`, `WebhookSource`,
  `FilesystemSource`) call `dispatch(event, retry=True)` — failures there are
  queued, retried with backoff, and eventually dead-lettered, because nothing
  is blocked waiting for the result.
- **Delivery resolution** always runs after a successful `Response`, regardless
  of `retry`: resolve an `Output` by `event.output` if set, otherwise by
  `event.source`. An *implicit* lookup (no `Output` registered under
  `event.source`) is skipped silently — most sources, including `"api"`, have
  no side-channel output and that's the normal case. An *explicit* lookup
  (`event.output` was set but nothing is registered under that name) raises
  `OutputNotFoundError` — the caller asked for a specific channel that doesn't
  exist, which is a programmer error, not a no-op.

### Broadcasting

```python
responses: dict[str, Response] = await runtime.broadcast(
    prompt="Review this architecture."
)
# {"claude": Response(...), "gemini": Response(...), "copilot": Response(...)}
```

Sends the same prompt to every registered target concurrently and returns a
dict keyed by target name. A target that raises is captured as an entry keyed
by name with the exception recorded on `metadata["error"]`, not raised to the
caller — one bad target should never take down a broadcast to the others.

### Events (fire-and-forget pub/sub)

```python
runtime.emit("invoice.created", invoice)

runtime.on("invoice.created", accounting_agent)      # a Target, called with the payload
runtime.on("invoice.created", lambda inv: log(inv))  # or any callable
```

`emit`/`on` are for the case where nobody needs a `Response` delivered anywhere
— just "let anyone interested know this happened." Internally, `emit` builds an
`Event(source="internal", target=<subscriber name>, payload=...)` per
subscriber and dispatches it, but delivery is skipped: no `Output` is invoked
for internally-emitted events unless a subscriber's own `Target.handle`
explicitly calls `runtime.send(...)` again.

### Scheduling

Scheduling is a `Source` (`waken.scheduler.Scheduler`) that the `Runtime`
registers by default under the name `"scheduler"`. Four decorators are sugar
over it:

```python
@runtime.every(hours=1)
async def hourly_summary():
    await runtime.send(target="claude", prompt="Summarize today's commits.")

@runtime.after(minutes=30)
async def follow_up():
    await runtime.send(target="claude", prompt="Any blockers yet?")

@runtime.at("2026-08-01T09:00:00")
async def launch_reminder():
    await runtime.send(target="claude", prompt="It's launch day.")

@runtime.cron("0 9 * * MON")
async def monday_report():
    await runtime.send(target="claude", prompt="Compile the weekly report.")
```

Every scheduled job is persisted to SQLite (`jobs` table) as soon as it's
registered, keyed by a stable id derived from the function's module + qualified
name. Restarting the process re-reads pending jobs from that table — schedules
survive restarts without the caller doing anything.

### HTTP

```python
runtime.serve(host="0.0.0.0", port=8080)
```

Exposes:

```
POST /send/{target}       body: {"prompt": "...", "session_id": "..."?}
POST /emit/{event}        body: <payload>
POST /webhook/{name}      body: <provider-specific>, routed by a registered WebhookSource
```

The HTTP source is registered by default (see [§3
Registration](#registration)), so `runtime.run()` alone is already reachable
over HTTP on the default bind address. `serve(host, port, blocking=True)` is
sugar for the common case of wanting to *choose* that bind address:

```python
def serve(self, host="127.0.0.1", port=8080, blocking=True):
    self._sources["http"] = HTTPSource(host, port)   # replaces the default binding
    if blocking:
        self.run()
        return None
    return asyncio.get_event_loop().create_task(self._run_async())
```

Call `serve(...)` when you care about the host/port; call plain `run()` when
you don't. Both start the same HTTP source — there is no second, separate
server. `blocking=False` returns an `asyncio.Task` and hands control of the
event loop back to the caller.

### Running everything

```python
runtime.run()
```

Synchronous, on purpose — like Flask's `app.run()`, this is the natural
bottom-of-script call, and a script that does nothing else with asyncio
shouldn't need to know `asyncio.run()` exists. It starts every registered
`Source` (calling `await source.start(runtime)` for each) and blocks until
interrupted (`Ctrl-C` / `SIGTERM`), then calls `await source.stop()` on each
in reverse registration order before returning. This is the only method most
`app.py` scripts call at the bottom of the file, and it's enough on its own
for `waken send`/`inspect` to reach the process (see [§8](#8-cli)) —
`serve()` is only needed to pick a non-default host/port.

Code embedding a `Runtime` inside a larger asyncio application (or a test)
that needs an *awaitable* equivalent uses the private `_run_async()` core
`run()` wraps — not part of the public API, since nothing in this project's
own scope needs it yet.

---

## 4. Sessions

```python
event = Event(
    source="slack",
    target="claude",
    payload={"prompt": "continue from before"},
    session_id=runtime.session("slack", external_key=slack_thread_ts),
)
```

`runtime.session(source, external_key)` returns a stable `session_id` for a
given `(source, external_key)` pair — minting one on first use, persisting it,
and returning the same id on every subsequent call for that pair. A
`FilesystemSource` calls this for you keyed by file path; a hypothetical Slack
integration would call it keyed by thread id (shown above). You only call it
directly when writing a custom `Source`.

The runtime never reads `payload` or stores conversation content — it stores
exactly one row per session: `(source, external_key, session_id, created_at,
last_seen_at)`. A `Target` receives the same `session_id` on every turn of one
conversation and is responsible for whatever history/state it wants to keep
keyed by it.

---

## 5. Writing a Target adapter

```python
# waken_claude/adapter.py
from waken import Event, Response, Target
from claude_agent_sdk import ClaudeSDKClient

class ClaudeAdapter(Target):
    def __init__(self, **client_kwargs):
        self._client = ClaudeSDKClient(**client_kwargs)
        self._sessions: dict[str, str] = {}   # waken session_id -> SDK session id

    async def handle(self, event: Event) -> Response:
        sdk_session = self._sessions.get(event.session_id)
        result = await self._client.query(
            event.payload["prompt"],
            resume=sdk_session,
        )
        if event.session_id:
            self._sessions[event.session_id] = result.session_id
        return Response(text=result.text, files=result.modified_files)
```

This is the entire shape of an adapter package: one class, one method, zero
dependency on `waken` beyond the three names imported at the top.

---

## 6. Writing a Source

```python
# a minimal webhook-style Source
import asyncio
from waken import Event, Runtime, Source

class PollingSource(Source):
    def __init__(self, target: str, interval_seconds: float = 5.0):
        self._target = target
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    async def start(self, runtime: Runtime) -> None:
        self._task = asyncio.create_task(self._loop(runtime))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self, runtime: Runtime) -> None:
        while True:
            for item in await self._poll_for_new_items():
                await runtime.dispatch(Event(
                    source="polling",
                    target=self._target,
                    payload={"prompt": item.text},
                ))
            await asyncio.sleep(self._interval)
```

---

## 7. Writing an Output

```python
from waken import Event, Output, Response

class SlackOutput(Output):
    def __init__(self, client):
        self._client = client

    async def deliver(self, event: Event, response: Response) -> None:
        channel = event.metadata["slack_channel"]
        await self._client.chat_postMessage(channel=channel, text=response.text)
        for path in response.files:
            await self._client.files_upload_v2(channel=channel, file=path)
```

A real `SlackOutput`/`SlackSource` pair — same reasoning as Target adapters —
ships as the separate `waken_slack` package rather than a core plugin, because
it requires a vendor SDK (`slack-sdk`) that has no business being a dependency
of `pip install waken`. The line isn't "is this a Target" so much as "does this
require a third-party client library" — see [ADR 0001](adr/0001-core-architecture.md#plugins-are-the-only-extension-mechanism).

---

## 8. CLI

```bash
waken run app.py                      # execute app.py, which calls runtime.run()
waken send claude "hello"             # POST /send/claude on a running instance
waken send claude "hello" --wait      # block and print the Response
waken emit invoice.created '{"id":1}' # POST /emit/invoice.created
waken inspect                         # show targets, sessions, jobs, queue depth
waken inspect --json                  # same, machine-readable
```

`waken send`/`emit`/`inspect` are HTTP clients against any running `Runtime`
(started via plain `run()` or via `serve()` — both expose the same HTTP source;
default `http://localhost:8080`, overridable with `--host`/`--port` or
`$WAKEN_URL`) — the same relationship the `docker` CLI has to `dockerd`.
`waken run` is the exception: it has no server to talk to yet, so it directly
executes the given script.

---

## 9. Error handling

- `runtime.dispatch(event)` always raises `TargetNotFoundError` immediately if
  `event.target` isn't registered — there's never a useful retry for "this name
  was never registered." `OutputNotFoundError` is raised only for an *explicit*
  `event.output` that isn't registered; an event with no `event.output` set
  that simply has no `Output` registered under its `event.source` name is not
  an error (see [§3, `dispatch()`](#dispatch)) — most sources have no
  side-channel output, and that's normal.
- What happens when a registered `Target.handle()` itself raises depends on
  `dispatch(event, retry=...)` (see [§3, `dispatch()`](#dispatch)):
  - `retry=False` (the default; used by `send()`/`send_sync()` and the HTTP
    `/send/{target}` route): the exception propagates immediately to the
    caller. Nothing is queued.
  - `retry=True` (used internally by `Scheduler`, `WebhookSource`,
    `FilesystemSource`, and any other Source with no synchronous caller
    waiting): the exception is caught, logged with a full traceback,
    persisted to the `queue` table with an incremented attempt count, and
    retried with exponential backoff (default: 3 attempts, capped at 5
    minutes) before being marked dead-lettered. `waken inspect` shows
    dead-lettered events; nothing is silently dropped.
- `runtime.broadcast()` never raises for an individual target's failure (see
  §3); it only raises if no targets are registered at all.

---

## 10. Full example

```python
from waken import Runtime
from waken.plugins.sources import FilesystemSource
from waken_slack import SlackOutput      # separate package — see §7
from waken_claude import ClaudeAdapter
from waken_gemini import GeminiAdapter

runtime = Runtime()

runtime.target("claude", ClaudeAdapter())
runtime.target("gemini", GeminiAdapter())

runtime.source("filesystem", FilesystemSource(watch="./inbox", target="claude"))
runtime.output("slack", SlackOutput(token="xoxb-..."))

@runtime.every(hours=6)
async def health_check():
    result = await runtime.send(target="claude", prompt="Any errors in the last 6h?")
    await runtime.send(target="gemini", prompt=f"Double check: {result.text}")

runtime.serve(port=8080)
```

Five lines of registration, one scheduled job, one line to go live. Nothing
here is a DAG, a workflow, or a plan — it's a routing table with a clock
attached.
