# Waken Implementation Plan

Each milestone below is independently testable: it ships working, tested code
and leaves the tree in a state where `pytest` is green before the next
milestone starts. Milestones are ordered so that every later milestone can be
built and tested against real earlier milestones — no milestone requires
stubbing out work that a later milestone will do.

Reference: [ADR 0001](adr/0001-core-architecture.md), [API Specification](api-spec.md).

---

## M0 — Scaffolding

**Goal:** an empty, correctly-shaped, installable package.

- `pyproject.toml` (Python 3.12+, `waken` package, `waken` console-script entry
  point pointing at a not-yet-implemented `waken.cli:main`)
- `waken/__init__.py`, `waken/events.py`, `waken/responses.py`,
  `waken/runtime.py`, `waken/router.py`, `waken/scheduler.py`,
  `waken/persistence.py`, `waken/server.py`, `waken/cli.py` — empty modules
- `waken/plugins/{sources,outputs,targets}/__init__.py`
- `tests/`, `examples/` directories
- Dev tooling: `ruff` (lint + format), `mypy` (strict), `pytest` +
  `pytest-asyncio`, pinned in a `dev` dependency group
- CI workflow running lint + typecheck + tests on push

**Done when:** `pip install -e ".[dev]"`, `ruff check .`, `mypy waken`, `pytest`
all pass on an empty tree with no test failures (because there are no tests
yet) and no import errors.

---

## M1 — Core types

**Goal:** `Event`, `Response`, and the `Target`/`Source`/`Output` protocols
exist exactly as specified in the [API spec](api-spec.md#2-core-types), with no
`Runtime` yet.

- `waken/events.py`: `Event` frozen dataclass
- `waken/responses.py`: `Response` dataclass
- `waken/protocols.py`: `Target`, `Source`, `Output` `Protocol`s
- `waken/targets.py`: `target_fn` decorator wrapping a plain async function into
  something satisfying `Target`
- `waken/exceptions.py`: `TargetNotFoundError`, `OutputNotFoundError`,
  `WakenError` base class

**Tests:**
- `Event` is immutable (mutating raises `FrozenInstanceError`); `event_id`
  auto-generates and is unique across instances; equality/repr behave
  sensibly.
- `Response` defaults (`files=[]`, `data={}`) are independent per instance (no
  shared-mutable-default bug).
- `target_fn`-wrapped function satisfies `isinstance(x, Target)` under
  `typing.runtime_checkable` (or an equivalent structural check used in
  `Runtime.target()` later — decide and lock this in now since M2 depends on
  it).

**Done when:** 100% of these types have unit tests, no `Runtime` code exists
yet, and the whole module tree still imports cleanly.

---

## M2 — Runtime registration and routing (in-memory)

**Goal:** `Runtime.target/source/output` registries and `Runtime.dispatch()`
work end-to-end with an in-memory-only runtime — no persistence, no HTTP, no
scheduler.

- `waken/runtime.py`: `Runtime.__init__` (no `db_path` behavior yet — accept and
  ignore, or defer the parameter; decide explicitly rather than half-wiring it)
- `runtime.target(name, target)`, `runtime.source(name, source)`,
  `runtime.output(name, output)`
- `runtime.dispatch(event, *, retry=False) -> Response`: look up target, await
  `.handle()`, return the `Response`; raise `TargetNotFoundError` for an
  unknown target. The `retry` parameter is accepted now (so the signature
  doesn't change in M6) but `retry=True` is a no-op until M6 adds the queue —
  a `Target.handle()` failure propagates immediately either way at this
  milestone.
- `runtime.send(target=..., prompt=..., **payload) -> Response` and
  `runtime.send_sync(...)` (wraps `send` via `asyncio.run` when no loop is
  running, matching the API spec's sync-wrapper contract)

**Tests:**
- Registering two targets and dispatching to each by name returns the correct
  adapter's `Response`.
- Dispatching to an unregistered target raises `TargetNotFoundError` with the
  target name in the message.
- `send_sync` works from a plain synchronous test function (no event loop
  already running) and raises a clear error if called from inside a running
  event loop (don't silently deadlock).
- A `Target.handle()` that raises propagates the exception out of `dispatch()`
  — this is the permanent `retry=False` contract (see [API spec
  §9](api-spec.md#9-error-handling)), not a placeholder M6 will change; M6
  adds the *separate* `retry=True` path used by Sources, it doesn't alter this
  one.

**Done when:** a test can build a `Runtime`, register two `target_fn`-wrapped
fakes, and assert correct routing — no SQLite file is created anywhere on disk
during this test run.

---

## M3 — Persistence and sessions

**Goal:** the SQLite-backed `sessions` table and `runtime.session()` exist, per
[API spec §4](api-spec.md#4-sessions).

- `waken/persistence.py`: `Database` wrapper around `sqlite3` — connect, create
  tables if absent, `PRAGMA user_version` schema-version check
- `sessions` table: `(source, external_key, session_id, created_at,
  last_seen_at)`, unique on `(source, external_key)`
- `Runtime(db_path=...)` now actually opens/creates the file (default:
  `.waken/waken.db` relative to CWD, directory auto-created)
- `runtime.session(source, external_key) -> str`: mint-or-return, update
  `last_seen_at`

**Tests:**
- First call to `runtime.session("slack", "T1")` returns a new id; second call
  with the same args returns the *same* id; a different `external_key` returns
  a *different* id.
- Constructing a second `Runtime` pointed at the same `db_path` sees sessions
  created by the first (proves persistence, not just in-memory caching).
- Deleting the db file and re-running is equivalent to first run (schema
  recreated correctly, no crash).
- No `db_path` given still works and creates `.waken/waken.db` under the test's
  temp working directory (use `tmp_path`/`monkeypatch.chdir` — never touch the
  real developer's filesystem in a test).

**Done when:** the full M2 test suite still passes unmodified (dispatch/routing
behavior didn't change), plus the new persistence/session tests above.

---

## M4 — Output delivery + Terminal output (first end-to-end slice)

**Goal:** the smallest possible complete vertical slice — dispatch resolving
and calling a real `Output` — proving Source → Runtime → Target → Response →
Output works for real, before HTTP or the CLI exist. There is no `CLISource`
in this design (per [API spec §2, `Source`](api-spec.md#source)) — the CLI is
an HTTP client built in M7, not a Source started by `run()`; this milestone is
purely about the delivery step of `dispatch()`.

- `waken/plugins/outputs/terminal.py`: `TerminalOutput` — writes
  `response.text` (and a note about `response.files`) to stdout
- `runtime.dispatch()` gains the delivery step, per [API spec §3,
  `dispatch()`](api-spec.md#dispatch): resolve an `Output` by `event.output` if
  set, else by `event.source`, and call `.deliver(event, response)` if one is
  registered. An *implicit* lookup (no `event.output`, nothing registered under
  `event.source`) skips delivery silently. An *explicit* lookup (`event.output`
  set, nothing registered under that name) raises `OutputNotFoundError` — this
  distinction is the contract, not an implementation detail, so get both paths
  under test now rather than picking just one.

**Tests:**
- Dispatching an `Event(source="terminal", ...)` with a `TerminalOutput`
  registered under `"terminal"` calls `deliver()` with the right `Response`
  (assert via a spy/mock, not real stdout capture, for determinism).
- Dispatching an event whose source has no matching registered output, and no
  `event.output` set, does *not* raise and still returns the `Response`.
- Dispatching an event with `event.output="nonexistent"` raises
  `OutputNotFoundError`.
- `event.output` override routes delivery to a different output than
  `event.source` would imply.

**Done when:** a test demonstrates the full loop — register a target and an
output, dispatch an event, assert both the returned `Response` and the
output's recorded delivery — with no HTTP server involved.

---

## M5 — Scheduler

**Goal:** `every`/`after`/`at`/`cron` decorators, backed by the `jobs` table,
survive process restart.

- `jobs` table: `(job_id, kind, spec, target_module, target_qualname,
  next_fire_at, created_at)`
- `waken/scheduler.py`: `Scheduler` (a `Source`) — on `start()`, loads pending
  jobs from the table and schedules them on the event loop; computes next-fire
  time for `every`/`cron` after each run and rewrites the row
- `runtime.every(**timedelta_kwargs)`, `runtime.after(**timedelta_kwargs)`,
  `runtime.at(iso_datetime)`, `runtime.cron(expression)` — all decorators
  registering the wrapped function with `Scheduler` and persisting a `jobs` row
  keyed by `f"{module}:{qualname}"`

**Tests:**
- `@runtime.every(seconds=...)` fires the wrapped coroutine repeatedly at
  roughly the right interval (use a short interval and a fake/controllable
  clock rather than real sleeps where possible, to keep the suite fast).
- `@runtime.after(...)` fires exactly once.
- `@runtime.at(...)` in the past fires immediately on `start()`; in the future,
  fires at the right time.
- `@runtime.cron(...)` computes the correct next-fire time for a known
  expression (test the cron-parsing logic in isolation, not just end-to-end).
- **Restart persistence:** register an `@runtime.every(...)` job, stop the
  runtime without letting it fire, construct a *new* `Runtime` against the same
  `db_path`, re-register the same decorated function, call `.run()` briefly,
  and confirm it still fires — proving the job survived in the `jobs` table,
  not just in memory.

**Done when:** all four scheduling primitives have direct unit tests plus one
restart-persistence integration test.

---

## M6 — Retry queue and dead-lettering

**Goal:** a failing `Target.handle()` is retried with backoff and eventually
dead-lettered, per [API spec §9](api-spec.md#9-error-handling), instead of
propagating raw (as M2 left it).

- `queue` table: `(event_id, event_json, attempt, next_attempt_at, status)`
  where `status` ∈ `pending|dead`
- `runtime.dispatch()`'s `retry=True` path becomes real (it was a no-op through
  M2–M5): built-in `WebhookSource` and `FilesystemSource` (M8) will call
  `dispatch(event, retry=True)` internally once they exist, since neither has
  a synchronous caller waiting on the result. `Scheduler` is *not* in this
  list — per M5, it calls a plain zero-argument handler (`Callable[[],
  Awaitable[Any]]`), never constructs an `Event`, and so never goes through
  `dispatch()` at all; if a scheduled handler wants retry semantics it calls
  `dispatch(event, retry=True)` itself, the same as any other caller.
  `send()`/`send_sync()` and the HTTP `/send/{target}` route keep calling
  `retry=False` — this milestone must not change their behavior (see the M2
  regression test below)
- Exponential backoff: default base 1s, factor 2, cap 5 minutes, max 3 attempts
  before marking `dead`
- `waken inspect` (stubbed until M7's CLI exists, but the underlying query
  function — "list dead-lettered events" — is written and tested now)

**Tests:**
- A `Target` that always raises: after 3 attempts (using a fast/fake clock, not
  real sleeps), the event is marked `dead` in the `queue` table and no further
  attempts are made.
- A `Target` that fails twice then succeeds: the third attempt's `Response` is
  the one delivered, and the queue row is removed (not left as `dead`).
- Backoff timing follows the documented formula (test the backoff calculation
  as a pure function, separately from the async retry loop).
- `runtime.send()`'s direct-raise behavior from M2 is unchanged by this
  milestone (regression test).

**Done when:** the retry/backoff logic is unit-tested as pure functions *and*
covered by one end-to-end "eventually dead-letters" integration test.

---

## M7 — HTTP server and CLI-as-HTTP-client

**Goal:** an `HTTPSource` registered by default (so plain `run()` is already
reachable), `runtime.serve()` as sugar for choosing a bind address, and the
real `waken send`/`emit`/`inspect` CLI talking over that same HTTP surface —
per [API spec §3](api-spec.md#http) and [§8](api-spec.md#8-cli).

This milestone also resolves two gaps the earlier plan text left implicit:

- **`run()` becomes synchronous.** The API spec's own Quickstart calls
  `runtime.run()` as a bare top-level statement, no `asyncio.run()` in sight —
  matching Flask's `app.run()`. M2–M6 built `run()` as a coroutine (fine for
  those milestones' own tests, which always awaited it directly), but that
  contradicts the documented ergonomics once a script actually needs to call
  it standalone. `run()` is now the sync, blocking, Flask-style entry point
  (`asyncio.run()` wrapped internally, with signal handlers converting
  Ctrl-C/SIGTERM into a cooperative cancellation so the `finally`-block
  Source cleanup always runs); the awaitable core moves to a private
  `_run_async()` that tests call directly.
- **`emit`/`on` move here from M9.** `/emit/{event}` and `waken emit` are both
  in this milestone's own scope, and neither means anything without
  `runtime.emit()`/`runtime.on()` existing yet — M9 having them as a separate,
  later milestone was an ordering mistake in the original plan. They're built
  here instead; M9 keeps only `broadcast()` (which has no HTTP/CLI dependency
  forcing it earlier) plus the spec-vs-implementation audit.

- `waken/server.py`: Starlette ASGI app with `POST /send/{target}`,
  `POST /emit/{event}`, `POST /webhook/{name}`, `GET /inspect`
- `waken/plugins/sources/http.py`: `HTTPSource`, wrapping uvicorn's `Server`
  with signal handling disabled (it must never install its own
  SIGINT/SIGTERM handlers — `run()`'s are the only ones), registered under
  `"http"` by `Runtime.__init__` by default
- `runtime.serve(host, port, blocking=True)`: re-registers `HTTPSource` with
  the given address, then calls `run()` (or schedules `_run_async()` as a
  task if `blocking=False`) — not a second server
- `runtime.emit(event_name, payload)` / `runtime.on(event_name, subscriber)`:
  fire-and-forget fan-out per [API spec §3](api-spec.md#events) — a `Target`
  subscriber gets a synthesized `Event`, a plain callable gets `payload`
  verbatim; no `Output` is ever invoked
- `runtime.inspect() -> dict`: registered target/source/output names plus
  job/queue counts, backing `GET /inspect`
- `waken/cli.py`: `waken run <script>`, `waken send <target> <prompt> [--wait]
  [--host] [--port]`, `waken emit <event> <json>`, `waken inspect [--json]` — all
  as a real HTTP client (via `httpx`) against `$WAKEN_URL` or `--host`/`--port`
  (default `http://localhost:8080`)

**Tests:**
- HTTP integration tests (using an ASGI test client, no real socket) for each
  route: `/send/{target}` dispatches and returns the `Response` as JSON;
  `/send/{unknown-target}` returns a clear 4xx with the error from
  `TargetNotFoundError`; `/inspect` reflects registered targets/sources/outputs
  and current queue/job counts.
- CLI tests invoke `waken send`/`inspect` against a test server instance (started
  in-process on a random free port for the test) and assert on stdout/exit
  code — not against a mocked HTTP layer, since the CLI's entire job *is* being
  an HTTP client.
- `waken run examples/quickstart.py` (see M10) actually starts and can be
  killed cleanly (`SIGTERM` triggers the `run()` shutdown path from
  [ADR 0001](adr/0001-core-architecture.md)).

**Done when:** a fresh clone can `pip install -e .`, run `waken run
examples/quickstart.py` in one terminal, and `waken send echo "hi"` in another,
and see the response — this is the plan's first fully-manual, "does this
actually feel like the API spec promised" checkpoint.

---

## M8 — Remaining zero-dependency built-in Sources/Outputs

**Goal:** `FilesystemSource`, `WebhookSource`, `NotificationOutput` — every
Source/Output that needs no third-party vendor SDK, on top of what M4–M7
already cover (HTTP/Scheduler/Terminal).

Voice, Slack, GitHub, and Email — the remaining entries in the original
brief's Source/Output lists — are **not** in this milestone or anywhere else
in this plan. Each requires a vendor SDK or platform-specific library
(`slack-sdk`, `PyGithub`, a speech engine), so each ships as its own optional
package (`waken-slack`, `waken-github`, `waken-voice`, `waken-email`) on the
same footing as a Target adapter — see [ADR 0001, "Plugins are the only
extension mechanism"](adr/0001-core-architecture.md#plugins-are-the-only-extension-mechanism)
and [API spec §7](api-spec.md#7-writing-an-output). Building `waken-slack` as
a worked example of that pattern is good follow-up work, but it's an adapter
package's milestone, not core's.

- `waken/plugins/sources/filesystem.py`: watches a directory. `watchfiles`
  (efficient OS-level file-event notification) is a third-party package,
  not stdlib, and this milestone's whole point is zero new dependencies — so
  this ships as a plain stdlib polling loop (`Path.iterdir()` on a timer),
  not `watchfiles`. Revisit as an opt-in upgrade later if polling proves too
  coarse for someone's use case; dispatches one `Event` per new file
- `waken/plugins/sources/webhook.py`: registers a named route under
  `POST /webhook/{name}` (via the M7 server) and hands the request body to a
  user-supplied parser callback that produces an `Event`. The route
  acknowledges immediately and dispatches in the background
  (`asyncio.create_task`, `retry=True`) rather than awaiting the dispatch
  before responding — a slow retry-with-backoff sequence must never hold
  open the webhook sender's HTTP connection (this applies equally to
  `FilesystemSource`'s own dispatch calls, for the same reason)
- `waken/plugins/outputs/notification.py`: desktop notification (platform
  library chosen at implementation time; must degrade to a no-op with a logged
  warning on unsupported platforms rather than crashing)

**Tests:**
- `FilesystemSource`: dropping a file into a watched (temp) directory results
  in exactly one dispatched `Event` with the file path in the payload; a file
  that already existed before `start()` does *not* fire (only new files).
- `WebhookSource`: POSTing to `/webhook/{name}` invokes the registered parser
  and dispatches the `Event` it returns; an unregistered webhook name returns
  404.
- `NotificationOutput`: on a platform without notification support in CI, the
  test asserts the no-op/warning path rather than being skipped silently.

**Done when:** every zero-vendor-dependency Source/Output in this plan's scope
(CLI-reachability via HTTP, Scheduler, Terminal, Filesystem, Webhook,
Notification) exists, is registered the same way a third-party plugin would
be, and has a test.

---

## M9 — `broadcast`

**Goal:** the one remaining piece of the [API spec's](api-spec.md) surface —
`runtime.broadcast()` — per §3. (`emit`/`on` moved to M7; see that
milestone's note.)

- `runtime.broadcast(**payload) -> dict[str, Response]`: fan out to all
  registered targets concurrently (`asyncio.gather`), capturing per-target
  exceptions into `Response(metadata={"error": ...})` entries rather than
  raising, as specified

**Tests:**
- `broadcast()` with 3 registered targets, one of which raises, returns 3
  entries — 2 real `Response`s and one with `metadata["error"]` set — and does
  not raise.
- `broadcast()` with zero registered targets raises (per spec: this is the one
  case it *does* raise).

**Done when:** every code example in the [API spec](api-spec.md) has a
corresponding passing test — at this point the spec and the implementation
should have zero known gaps.

---

## M10 — Polish, docs, examples, v0.1.0

**Goal:** ready to publish.

- `examples/quickstart.py` (the exact Quickstart from the API spec, running
  against a trivial `echo` target shipped for demos/tests — not a real LLM
  adapter, so examples run with no API keys)
- `examples/scheduler.py`, `examples/broadcast.py`, `examples/webhook.py` —
  one runnable example per major feature area
- `README.md`: quickstart fits on one screen, per the brief's own bar
- Docstrings audited across the public API (everything importable from
  `waken` top-level has one)
- `mypy --strict` clean across the whole package
- Test coverage report reviewed for gaps (target: high coverage on
  `runtime.py`, `router.py`/dispatch logic, `persistence.py`, `scheduler.py` —
  the pieces named explicitly in the original brief's Testing section)
- Tag `v0.1.0`, publish to PyPI as `waken`

**Done when:** someone who has never seen this project can read the README,
run the quickstart, and understand what Waken does in five minutes — the
brief's own success bar for the README.

---

## Explicitly out of scope for this plan

Real Target adapters (`waken-claude`, `waken-gemini`, `waken-copilot`) and any
Source/Output requiring a vendor SDK (`waken-slack`, `waken-github`,
`waken-voice`, `waken-email`) are **separate packages with their own release
cadence**, not milestones of the core repo — per [ADR
0001](adr/0001-core-architecture.md), core must never depend on them, and this
plan mirrors that by not building them here. The `echo` target used in M10's
examples is the only "adapter" this plan ships, and it exists purely so
examples run without API keys.
