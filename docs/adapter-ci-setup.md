# CI Setup for Adapter Repos

How every `waken-*` adapter repo should set up their GitHub Actions config,
and why it isn't shared automatically across repos. Two kinds of adapter
exist so far, both following the conventions below: **Target** adapters
(`waken-claude`, `waken-gemini`, `waken-copilot`, `waken-openai`,
`waken-mistral`, `waken-cohere`, `waken-bedrock`, `waken-ollama`,
`waken-groq` — wrap an AI-agent backend) and **channel** adapters
(`waken-voice`, `waken-slack`, `waken-telegram` — implement `Source`/`Output`
instead, since a channel isn't an AI backend).

## Why this isn't automatic (yet)

`waken` now lives under the **WakenHQ** GitHub Organization (it moved there
from an interim personal-account home — Homepage/badges/Trusted-Publisher
config all had to be updated again as part of that, same churn this doc
already warned a future org migration would cause). An Organization
*can* share secrets/variables across every repo in it, so the
infrastructure reason for per-repo config is gone.

What hasn't happened yet is actually switching to that sharing: each
adapter repo still gets its own repo-level `PYTHON_VERSION` variable rather
than one org-level `WakenHQ`-wide variable, purely because nobody has done
that consolidation pass — not because it's blocked. Provider API-key
secrets (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, ...) should stay
**repo-level regardless**, org-wide or not: each adapter needs a different
credential, so there's nothing to gain from sharing those specifically, and
real reasons not to (an org-wide `ANTHROPIC_API_KEY` would be visible to
`waken-gemini`'s CI too, which has no reason to hold Anthropic's key).

## Convention: name secrets after the provider SDK, not Waken

An adapter's CI needs whatever credential the *provider's own SDK* expects
— use that exact name, don't invent a `WAKEN_*` variant:

| Adapter | Secret name | Matches |
|---|---|---|
| `waken-claude` | `ANTHROPIC_API_KEY` | `claude-agent-sdk`'s own default env var |
| `waken-gemini` | `GEMINI_API_KEY` | `google-genai`'s own default env var — but it actually checks `GOOGLE_API_KEY` first and prefers it if *both* are set (confirmed from SDK source); don't set both |
| `waken-copilot` | none | The `copilot` CLI authenticates via OAuth device flow (`copilot`/`gh auth login`), not a static credential — there's nothing to put in a secret. Its CI can only unit-test with the subprocess call mocked; real integration testing isn't feasible unattended. |
| `waken-openai` | `OPENAI_API_KEY` | `openai`'s own default env var |
| `waken-mistral` | `MISTRAL_API_KEY` | `mistralai`'s own default env var (read lazily, per-request, not at client construction) |
| `waken-cohere` | `COHERE_API_KEY` | `cohere`'s own SDK checks `CO_API_KEY` first, then falls back to `COHERE_API_KEY` |
| `waken-groq` | `GROQ_API_KEY` | `groq`'s own default env var |
| `waken-bedrock` | none | Authenticates via the standard AWS credential chain (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_PROFILE`/instance role/...), not a single named secret — don't invent one. |
| `waken-ollama` | none | Local-only; no API key at all. Optional `OLLAMA_HOST` if the daemon isn't at the default `localhost:11434`. |

Reusing the SDK's own name means adapter code and CI never need a
translation layer, and a contributor running tests locally already has the
right env var set from using the SDK directly elsewhere.

## Channel adapters (Source/Output) have their own secret shape

`waken-voice`, `waken-slack`, and `waken-telegram` don't wrap an AI backend —
they wrap a *channel* (see [ADR 0001](adr/0001-core-architecture.md)'s
`Source`/`Output` protocols). Their secrets:

| Adapter | Secret(s) | Notes |
|---|---|---|
| `waken-voice` | `OPENAI_API_KEY` | Reuses OpenAI's audio API (Whisper for STT, TTS for speech) — same key as `waken-openai`, unrelated package. |
| `waken-slack` | `SLACK_APP_TOKEN` **and** `SLACK_BOT_TOKEN` | Two secrets, not one — an app-level token (`xapp-...`) for the Socket Mode connection `SlackSource` holds open, and a bot token (`xoxb-...`) for `SlackOutput`'s `chat.postMessage` calls. |
| `waken-telegram` | `TELEGRAM_BOT_TOKEN` | From @BotFather. |

`waken-slack` and `waken-telegram` both deliberately avoid HTTP webhooks
(Socket Mode and long polling, respectively) for the same underlying reason:
core `waken`'s `WebhookSource` doesn't currently give a registered parser
access to request headers, which blocks HMAC-signature-verified webhooks —
see the "Webhook signature verification" entry in [ADR 0001's Future
Evolution](adr/0001-core-architecture.md#future-evolution).

## Convention: one repo variable for the Python version

Every repo's `ci.yml`/`publish.yml` reference `${{ vars.PYTHON_VERSION ||
'3.12' }}` rather than hardcoding the version string in multiple places
within that repo. The `|| '3.12'` fallback matters specifically because
forked-repo pull requests don't get access to the base repo's
variables — without it, CI would break for outside contributors.
This is a single-source-of-truth-*within-one-repo* convention, not
cross-repo sharing (see above for why that's not available).

## Setting up a new adapter repo

```bash
gh variable set PYTHON_VERSION --repo WakenHQ/<adapter-repo> --body "3.12"

# Run this one yourself, in your own terminal — don't paste a real API key
# into a chat with an assistant, regardless of which one:
gh secret set ANTHROPIC_API_KEY --repo WakenHQ/<adapter-repo>
```

Then copy `waken`'s `.github/workflows/ci.yml` and `publish.yml` as a
starting point (same `pip install -e ".[dev]"` / ruff / mypy / pytest
shape applies to every adapter), adjusting only whatever step actually
needs the provider secret (e.g. an integration-test job).

**Gotcha, actually hit while building the first 12 adapters:** both
`ci.yml` *and* `publish.yml` have their own `mypy waken` line (`publish.yml`
has a full `test` job, not just `ci.yml`) — copying `publish.yml` and only
updating `ci.yml`'s mypy target leaves `publish.yml` silently mypy-checking
core `waken` instead of the adapter's own package. It won't fail the
build (`waken` has no mypy errors to trip on), so nothing signals the
mistake — it just means the release pipeline's type check isn't actually
checking the thing being released. Grep both workflow files for `mypy `
after copying, not just one.

## A future improvement worth knowing about, not built yet

GitHub Actions supports **reusable workflows** (`workflow_call`) — `waken`
could host one canonical `ci.yml`/`publish.yml` that every adapter repo
calls into with a one-line `uses: WakenHQ/waken/.github/workflows/...@main`,
instead of copy-pasting the file per repo. This solves duplicated *workflow
logic* (a different problem than shared secrets) and would need its
Trusted Publishing / OIDC interaction verified carefully against PyPI's
current docs before relying on it for `publish.yml` specifically — flagged
here as a good next step, not implemented, since it wasn't what was asked
for yet.
