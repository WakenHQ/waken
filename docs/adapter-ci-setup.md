# CI Setup for Adapter Repos

How `waken-claude`, `waken-gemini`, `waken-copilot`, and any other adapter
repo should set up their GitHub Actions config, and why it isn't shared
automatically across repos.

## Why this isn't automatic

GitHub Actions supports secrets/variables shared across every repo in an
**Organization**. `waken-dev` is a regular GitHub *user* account, not an
Organization (confirmed via `gh api users/waken-dev` → `"type": "User"`),
so that sharing mechanism isn't available. Each repo gets its own
repo-level secrets and variables — see [ADR
0001](adr/0001-core-architecture.md) for the unrelated reason adapters are
separate *packages*; this is the separate, purely-infrastructure reason
their *CI config* is also separate per repo.

If the ecosystem outgrows this, the fix is creating an actual Organization
(picking a new name — `waken-dev` itself isn't available for an org, since
users and orgs share one namespace) and transferring repos into it. That's
a real migration (Homepage/badges/Trusted-Publisher config all need
updating again, same as when `waken` itself moved to the `waken-dev`
account), not a switch to flip — do it deliberately, not reactively.

## Convention: name secrets after the provider SDK, not Waken

An adapter's CI needs whatever credential the *provider's own SDK* expects
— use that exact name, don't invent a `WAKEN_*` variant:

| Adapter | Secret name | Matches |
|---|---|---|
| `waken-claude` | `ANTHROPIC_API_KEY` | Anthropic SDK's own env var |
| `waken-gemini` | `GOOGLE_API_KEY` (or whatever the Gemini SDK in use actually reads — check at the time) | Google SDK's own env var |
| `waken-copilot` | whatever GitHub's Copilot API surface requires at the time | — |

Reusing the SDK's own name means adapter code and CI never need a
translation layer, and a contributor running tests locally already has the
right env var set from using the SDK directly elsewhere.

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
gh variable set PYTHON_VERSION --repo waken-dev/<adapter-repo> --body "3.12"

# Run this one yourself, in your own terminal — don't paste a real API key
# into a chat with an assistant, regardless of which one:
gh secret set ANTHROPIC_API_KEY --repo waken-dev/<adapter-repo>
```

Then copy `waken`'s `.github/workflows/ci.yml` and `publish.yml` as a
starting point (same `pip install -e ".[dev]"` / ruff / mypy / pytest
shape applies to every adapter), adjusting only whatever step actually
needs the provider secret (e.g. an integration-test job).

## A future improvement worth knowing about, not built yet

GitHub Actions supports **reusable workflows** (`workflow_call`) — `waken`
could host one canonical `ci.yml`/`publish.yml` that every adapter repo
calls into with a one-line `uses: waken-dev/waken/.github/workflows/...@main`,
instead of copy-pasting the file per repo. This solves duplicated *workflow
logic* (a different problem than shared secrets) and would need its
Trusted Publishing / OIDC interaction verified carefully against PyPI's
current docs before relying on it for `publish.yml` specifically — flagged
here as a good next step, not implemented, since it wasn't what was asked
for yet.
