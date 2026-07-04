> **Archived — historical input, not maintained documentation.**
> This is the original task brief given to the AI agent that researched and
> designed this project. It is kept for provenance, not as a source of truth:
> where it conflicts with [prior-art.md](../prior-art.md),
> [adr/0001-core-architecture.md](../adr/0001-core-architecture.md),
> [api-spec.md](../api-spec.md), or [implementation-plan.md](../implementation-plan.md),
> those derived documents win. The project name below is a placeholder; the
> actual decision is in [name-research.md](../name-research.md).

# Build a New Open-Source AI Infrastructure Project

> **IMPORTANT**
>
> This project is intended to become foundational infrastructure for AI agents.
>
> Think carefully before writing any code.
>
> Spend significantly more time designing than implementing.
>
> The goal is not to build another agent framework.
>
> The goal is to build a missing piece of infrastructure that could eventually become a dependency of many agent frameworks.

---

# Phase 0 — Research First

Before writing any code:

1. Research the current ecosystem.
2. Compare existing projects.
3. Identify gaps.
4. Design the architecture.
5. Design the public API.
6. Only then begin implementation.

Do **not** immediately start coding.

---

# Project Name

Before implementation, determine the project's name.

Requirements:

- one word preferred
- memorable
- easy to pronounce
- easy to search
- appropriate for open source
- appropriate for infrastructure
- vendor neutral
- future proof

Research at least **20 candidate names**.

For every candidate:

- search PyPI
- search GitHub
- eliminate collisions
- avoid well-known projects
- avoid confusing names
- avoid trademark issues where practical

Choose the strongest available name.

Once selected:

- use it everywhere
- package name
- imports
- CLI
- README
- documentation
- examples
- tests

Do not use placeholder names.

---

# Prior Art Review

Research projects including (but not limited to):

- OpenAI Agents SDK
- LangGraph
- CrewAI
- AutoGen
- MCP
- Claude Code
- Gemini CLI
- GitHub Copilot
- Airflow
- Celery
- Temporal
- NATS
- Redis Pub/Sub
- FastAPI

For each project explain:

- what it solves
- where it overlaps
- what it does not solve
- what ideas should be borrowed
- what should intentionally NOT be copied

Then explain why this project deserves to exist.

---

# Deliverables Before Coding

Produce these documents first.

## 1. Architecture Decision Record (ADR)

Explain:

- problem statement
- architecture
- alternatives considered
- rejected alternatives
- tradeoffs
- future evolution

---

## 2. Public API Specification

Design the API first.

Do not implement anything until the API feels elegant.

Include many examples.

If implementation later disagrees with the API, change the implementation—not the API.

The API is the product.

---

## 3. Implementation Plan

Break implementation into milestones.

Each milestone should be independently testable.

---

# Vision

Build a lightweight runtime that connects humans, applications, services and AI agents.

The runtime receives work.

Routes it.

Returns the response.

Nothing more.

It is intentionally **not**:

- an agent framework
- an orchestration engine
- a workflow builder
- a DAG system
- an LLM wrapper
- a planning framework
- an AI operating system

Think of it as:

- nginx for AI agents
- reverse proxy for AI
- router for agents
- event router
- activation layer

---

# Philosophy

The project should feel like:

- Flask
- Requests
- Click
- FastAPI

Small.

Elegant.

Composable.

Easy.

Obvious.

Not like:

- Airflow
- Temporal
- Kubernetes
- LangGraph

---

# Guiding Principle

Every feature must answer exactly one question.

> How does work travel from a source to the correct AI agent, and how does the result return?

If it doesn't improve that flow, it does not belong.

---

# Priorities

Order of importance:

1. Beautiful API
2. Simplicity
3. Developer experience
4. Minimal dependencies
5. Extensibility
6. Reliability
7. Performance

---

# Installation

The ideal experience:

```bash
pip install <project-name>
```

Done.

No Docker.

No Redis.

No RabbitMQ.

No PostgreSQL.

No Kubernetes.

No external services.

Everything should work immediately.

---

# Architecture

Separate into two packages.

## Core

Contains:

- router
- scheduler
- persistence
- event bus
- transports
- outputs
- HTTP server
- CLI

Very few dependencies.

---

## Adapters

Optional integrations.

Examples:

- Claude Code
- Gemini CLI
- GitHub Copilot
- OpenAI Agents SDK
- LangGraph
- CrewAI
- AutoGen

Core must never depend on adapters.

---

# Core Concepts

Everything revolves around five concepts.

---

## Source

Creates work.

Examples:

- CLI
- HTTP
- Voice
- Slack
- Discord
- GitHub
- Email
- Filesystem
- Scheduler
- WebSocket
- Another agent

---

## Target

Receives work.

```python
runtime.target(
    "claude",
    ClaudeAdapter()
)
```

```python
runtime.target(
    "gemini",
    GeminiAdapter()
)
```

```python
runtime.target(
    "copilot",
    CopilotAdapter()
)
```

Targets must be interchangeable.

---

## Event

Everything becomes an Event.

```python
Event(
    source="voice",
    target="claude",
    payload={
        "prompt":"Build tic tac toe"
    }
)
```

---

## Response

Every target returns:

```python
Response(
    text="Done.",
    files=[
        "game.py"
    ]
)
```

---

## Output

Outputs deliver Responses.

Examples:

- terminal
- voice
- Slack
- GitHub
- email
- push notification
- desktop notification

---

# Public API

The API should be tiny.

```python
from project import Runtime

runtime = Runtime()

runtime.target(
    "claude",
    ClaudeAdapter()
)

runtime.run()
```

---

Send work.

```python
runtime.send(
    target="claude",
    prompt="Build tic tac toe."
)
```

---

Broadcast.

```python
runtime.broadcast(
    prompt="Review this architecture."
)
```

---

Events.

```python
runtime.emit(
    "invoice.created",
    invoice
)
```

---

Subscriptions.

```python
runtime.on(
    "invoice.created",
    accounting_agent
)
```

---

# Routing

Routing is the core feature.

Input:

```
Hey Claude,

Build me tic tac toe.
```

Produces:

```python
Event(
    source="voice",
    target="claude",
    payload={
        "prompt":"Build me tic tac toe."
    }
)
```

The runtime routes the Event.

Claude returns:

```python
Response(...)
```

The runtime automatically returns the response using the appropriate Output.

Examples:

Voice

↓

Voice

CLI

↓

Terminal

GitHub

↓

GitHub comment

HTTP

↓

HTTP response

---

# Sources

Everything should be a plugin.

Built-in:

CLI

HTTP

Scheduler

Filesystem

Webhooks

Voice

Voice should use a provider abstraction.

Compatible with engines like:

- OpenAI Realtime
- Whisper
- Vosk
- Picovoice
- Windows Speech
- macOS Speech

The runtime should never depend on one provider.

---

# Outputs

Outputs are plugins.

Built-in:

- Terminal
- Voice
- GitHub
- Slack
- Email
- Notifications

Voice output should support multiple TTS engines.

---

# Sessions

Support conversations.

The runtime manages:

- session IDs
- routing

Adapters manage:

- conversation history
- model state

---

# Scheduler

Scheduling is another Source.

Support:

```python
runtime.every(...)
```

```python
runtime.after(...)
```

```python
runtime.at(...)
```

```python
runtime.cron(...)
```

Persist jobs with SQLite.

---

# Persistence

SQLite.

Automatically created.

Persist:

- scheduled jobs
- retries
- queued events
- sessions

Zero configuration.

---

# HTTP

One line.

```python
runtime.serve()
```

Endpoints.

```
POST /send/{target}

POST /emit/{event}

POST /webhook/{name}
```

---

# CLI

Provide:

```bash
project run app.py

project send claude "hello"

project inspect
```

Show:

- registered targets
- active sessions
- scheduled jobs
- queued events

---

# Plugin System

Everything should be replaceable.

Sources.

Targets.

Outputs.

No modification to the core should be required.

---

# Logging

Readable.

Example.

```
Voice

↓

Claude

↓

Completed

512 ms
```

Errors should include useful tracebacks.

---

# File Structure

```
project/

    router.py
    scheduler.py
    events.py
    responses.py
    persistence.py
    server.py
    cli.py

    plugins/

        sources/

        outputs/

        targets/

tests/

examples/

README.md
```

Small modules.

Small functions.

Modern Python.

---

# Code Style

Python 3.12+

asyncio

type hints

dataclasses

excellent docstrings

minimal dependencies

composition over inheritance

clarity over cleverness

---

# Testing

High coverage.

Test:

- routing
- scheduler
- persistence
- HTTP
- retries
- sessions
- plugin loading
- event bus

---

# README

Someone should understand the project in five minutes.

The quickstart should fit on one screen.

---

# Non-goals

Do NOT build:

- DAGs
- orchestration
- planners
- vector databases
- memory
- prompt management
- workflow editors
- distributed execution
- Kubernetes support
- message brokers
- AI frameworks

Remain laser-focused.

---

# Success Criteria

The finished project should become the easiest way to connect humans, software, and AI agents.

Whether work comes from:

- voice
- HTTP
- CLI
- GitHub
- email
- scheduler
- another AI agent

the developer should only think about:

```
Source

↓

Runtime

↓

Target

↓

Response

↓

Output
```

The implementation should be elegant, production-ready, and easy to extend.

It should solve one problem exceptionally well:

> Receive work, route it to the correct AI agent, and return the result through the appropriate channel.

If, during implementation, you discover a simpler architecture or a more elegant API that better satisfies this vision, prefer the simpler design—even if it requires refactoring earlier work. The long-term quality of the project is more important than preserving initial implementation decisions.