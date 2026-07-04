# Project Name Research

**Decision: Waken.**

The project brief required researching at least 20 candidate names, checking
PyPI/GitHub for collisions, and eliminating anything colliding with a
well-known or trademark-flagged project before picking one. This document
records that research and the resulting decision.

## Method

63 one-word candidates were brainstormed around routing/gateway/relay/
dispatch/bridge/activation/connection/signal/switchboard themes, deliberately
avoiding names derivative of any project compared against in the [Prior Art
Review](prior-art.md) (LangGraph, CrewAI, AutoGen, Temporal, Celery, NATS,
Airflow, FastAPI, MCP, Claude, Gemini, Copilot). Each candidate was checked
against:

- **PyPI**: `curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/<name>/json` — a `404` means the exact package name is free.
- **GitHub**: `gh search repos <name>` plus `gh api users/<name>` / `gh api orgs/<name>`, to catch a prominent existing project or claimed org/user namespace under the same name.
- **General web**: a search for `"<name> github"` / `"<name> python"` to catch collisions outside GitHub — an existing SaaS product, a funded startup, a well-known package in another ecosystem.

A dormant personal GitHub account with 0–2 unrelated repos sitting on the bare
username was **not** treated as disqualifying (GitHub shares one namespace
across users and orgs, so nearly every short word has one) — only a
prominent, active, relevantly-named project or organization was.

## Results

Of 63 candidates, the large majority were eliminated on an exact PyPI or
GitHub collision — the obvious metaphors in this space (Relay, Bridge,
Gateway, Hub, Conduit, Beacon, Signal, Dispatch, Switchboard, Herald, Usher,
Chorus, Concierge, Emissary, Waystation, Junction, Turnstile, Vessel, and
~40 others) are already taken by a prominent or exact-match project. The
clear and near-clear survivors:

| Candidate | Status | Rationale |
|---|---|---|
| **Waken** | Clear | Real verb, no pronunciation ambiguity, zero collisions found anywhere. Matches the "activation layer" positioning directly: the runtime wakes the right agent. |
| **Relayo** | Clear | Distinctive coinage on "relay" (receive → hand off), avoiding the taken bare word. Leans into router framing over activation framing. |
| **Hailer** | Clear* | "To hail" = summon/signal from a distance. Zero functional/trademark collisions. *Soft risk: visually one letter from "healer."* |
| **Ignitor** | Clear* | "The small component that starts a bigger process." No exact-name collision. *Soft risk: phonetic neighbor to Apache Ignite / Weaveworks Ignite (unrelated products, shared root word).* |
| **Wayside** | Clear* | Avoids the "waystation" collision (an existing MCP-integration-hub product with near-identical positioning). *Soft risk: the idiom "fall by the wayside" carries a neglected/abandoned connotation.* |
| **Waker** | Risky → Clear | No direct collision, but the "wake-word detection" audio-tooling space is thematically crowded. |
| **Wakely** | Risky → Clear | No collision, but reads as a surname — weaker brand distinctiveness. |
| **WakeIt** | Clear | Checked separately (see below) after the repository itself turned out to already be using this name. |

Full detail on eliminated candidates (PyPI-taken, GitHub-collision, or
trademark-flagged) is preserved in the research agent transcript this table
summarizes; the eliminated set is not reproduced here since none of it
survived to the decision point.

## "WakeIt" — checked separately

The repository this project lives in was already named `WakeIt` before this
naming research started. Because the independent research above converged on
`Waken` — the same root, arrived at with no knowledge of the repo name — it was
worth checking `WakeIt` itself before treating that as a coincidence to
ignore:

```
PyPI wakeit:   404 (free)
PyPI wake-it:  404 (free)
GitHub org "wakeit":   does not exist
GitHub user "wakeit":  exists, dormant (0 public repos, 1 follower) — not disqualifying per the criteria above
GitHub repos matching "wakeit": two small, unrelated Wake-on-LAN utilities (nathan-osman/wakeit, fxjung/wakeit)
```

`WakeIt` is clear by the same criteria applied to every other candidate.

## Decision

Presented to the project owner as a shortlist of the zero-caveat options
(`WakeIt`, `Waken`, `Relayo`) plus the full table above on request. Decision:
**Waken** — the same activation-layer metaphor as `WakeIt`, judged to read
more like serious infrastructure as a bare verb, still zero collisions.

This name is now used consistently: package name (`pip install waken`),
import name (`from waken import Runtime`), CLI command (`waken`), and
throughout the [ADR](adr/0001-core-architecture.md), [API
spec](api-spec.md), and [implementation plan](implementation-plan.md).
