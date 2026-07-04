# Prior Art Review

**Project:** Waken — a lightweight runtime that routes work from a Source, to an
interchangeable AI-agent Target, back through an Output.

**Date:** 2026-07-04
**Method:** ~25 independently-researched projects/products, each checked against
primary docs/READMEs/GitHub as of mid-2026 (not from training-data recall).

This document answers one question per project: **does anything already do
"receive work from an arbitrary Source, route it to an interchangeable AI-agent
Target, deliver the Response through a pluggable Output" as a small, generic,
self-hostable library?** The short answer, defended below: no. Everything found
solves an adjacent axis, and most of what looks like a match on the surface
inverts the direction (agent-outward, not source-inward) or bundles scope this
project explicitly rejects (memory, orchestration, DAGs).

---

## 1. Agent frameworks (orchestrate *within* a run, not *across* transports)

| Project | What it solves | Why it's not this project |
|---|---|---|
| **LangGraph / LangChain** | Low-level graph orchestration for stateful, durable, multi-step agents (`StateGraph`, `Command`, checkpointing). | Routes between *nodes in one graph invocation*, not external channels. No Source/Target/Output types anywhere. LangServe (the one "expose a chain over HTTP" piece) is deprecated and its repo archived (2026-05-05). The only first-party multi-channel connector (`langgraph-messaging-integrations`) supports exactly one platform (Slack), hard-coded, non-generalized. |
| **CrewAI** | Role-playing agent "crews" cooperating via `Process.sequential`/`hierarchical`; `Flows` add `@start/@listen/@router` event-decorator control flow. | `@router` branches on the *flow's own* prior method output, not on an inbound event's source. The only real "Source" analog (Enterprise Triggers: Slack/Gmail/HubSpot/etc.) is a closed, paid, ~10-connector catalog — confirmed by CrewAI's own community that OSS-edition remote triggering requires hand-rolling a FastAPI wrapper. |
| **AutoGen / AG2 / Microsoft Agent Framework** | Multi-agent conversation (`GroupChat`, speaker selection) and, in MAF, graph-based `Workflow` orchestration with typed handoffs. | Routes among agents *already instantiated in one process* (`groupchat.agents`, `WorkflowBuilder`). Slack/Discord/Telegram appear only as pull-based *tools* an agent calls, never as inbound triggers. MAF's `ChatClient` abstraction is the closest "interchangeable Target" analog in the entire survey — one call surface, many model backends — but it swaps the *model under one agent*, not the *agent answering an external event*. |
| **OpenAI Agents SDK** (successor to Swarm) | Provider-agnostic (100+ LLMs via LiteLLM) multi-agent handoffs, guardrails, sessions, tracing. | `handoff()` delegates control *within one conversation graph*. No Source abstraction — every integration found (Slack via MCP, email via AgentMail) is bespoke glue written by a third party, not an SDK feature. Sessions manage conversation history only, never routing. |
| **Google Gemini CLI / Antigravity** | Terminal ReAct-loop coding agent. | Single fixed backend (Gemini only — multi-provider is an open, unimplemented issue). No inbound HTTP/webhook listener, no native scheduler (feature request closed as backlog). Multi-channel = N bespoke integrations (GitHub Actions has its own dispatcher), not one abstraction. |
| **GitHub Copilot / Agent HQ / Mission Control** | Multi-*vendor*-agent picker (Copilot, Claude, Codex, Jules, Devin) triggerable from GitHub events, Slack, Teams, Jira, Linear. | Closest *surface-level* pitch to this project found anywhere ("any agent, any way you work"). But it's a closed dashboard — no documented common request/response schema across vendors, no programmable "route this Event to whichever Target I configure" API. Output is always GitHub-object-shaped (PR/comment/commit) or the originating tool's timeline; there is no decoupled Output concept. |
| **Vercel AI SDK, Mastra.ai, Cloudflare Agents SDK, Letta** | TS/JS unified model-calling SDKs, workflow engines, and a persistent-memory agent framework, respectively. | All four are squarely inside this project's own non-goals (LLM wrapper, DAG/workflow engine, memory framework) and/or wrong language ecosystem (TypeScript, not Python). Flagged for completeness; none are close. |

**Pattern across every agent framework surveyed:** the unit of work is "a run/conversation," addressed by an `Agent`/`Runner`/`Crew`/`Workflow` object that already exists in the calling process. None represent "a unit of inbound work from an external system" as a first-class, transport-agnostic type — which is exactly this project's `Event`.

Primary sources for the table above: [github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph),
[github.com/langchain-ai/langserve](https://github.com/langchain-ai/langserve) (archived),
[docs.crewai.com/en/concepts/flows](https://docs.crewai.com/en/concepts/flows),
[community.crewai.com/t/trigger-crewai-flow-remotely/7276](https://community.crewai.com/t/trigger-crewai-flow-remotely/7276),
[learn.microsoft.com/en-us/agent-framework/overview](https://learn.microsoft.com/en-us/agent-framework/overview/),
[github.com/openai/openai-agents-python](https://github.com/openai/openai-agents-python),
[github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli),
[github.blog/news-insights/company-news/welcome-home-agents](https://github.blog/news-insights/company-news/welcome-home-agents/).

---

## 2. MCP and A2A — real, open, and *complementary*, not competing

**Model Context Protocol (MCP).** Standardizes how an already-running agent
("Host") discovers and calls external tools/context ("Servers"). This is the
mirror image of the problem this project solves: MCP governs what an agent does
*after* it's already decided to act; this project governs *what triggers the
agent in the first place and where the answer goes*. MCP's own roadmap
admits the adjacent gap explicitly: "Gateway and proxy patterns: well-defined
behavior when a client does not connect directly to a server but routes through
an intermediary... much of the output will likely land as extensions rather
than core spec changes" [modelcontextprotocol.io/development/roadmap](https://modelcontextprotocol.io/development/roadmap)
— i.e., even MCP's maintainers know this layer is unsolved *for MCP's own
axis*, let alone for arbitrary human-facing Sources. Notably, MCP's Sampling
feature (the one place a tool server could "borrow" a connected LLM) is being
**deprecated**: as of this writing (2026-07-04) the deprecation is locked into
a Release Candidate (frozen 2026-05-21) scheduled for publication as spec
revision `2026-07-28` — not yet the live spec, but the decision itself is
already made and documented, with a deprecation warning already visible on the
draft [modelcontextprotocol.io/specification/draft/client/sampling](https://modelcontextprotocol.io/specification/draft/client/sampling).
The protocol walking back its one LLM-wrapper-adjacent feature validates this
project's non-goal of not being an LLM wrapper either.

**Agent2Agent (A2A).** An open, Linux-Foundation-governed wire protocol for
*agent-to-agent* task delegation and capability discovery (Agent Cards)
[a2a-protocol.org/latest](https://a2a-protocol.org/latest/). A2A's own docs
explicitly disclaim the Source side: "Not an interactive messaging app like
Slack, Discord, WhatsApp, or Telegram. A2A is a machine-to-machine protocol for
autonomous agents." A2A validates the *idea* that "target must be
interchangeable, discoverable via a small card/manifest" is a legitimate,
vendor-neutral design pattern — worth studying as a future wire format for
Target adapters — but it is not a router and does not touch human/app Sources.

**Agent Client Protocol (ACP)** [agentclientprotocol.com](https://agentclientprotocol.com/),
created by Zed, is the closest wire-protocol analog to "interchangeable
Target" found in this entire survey: any ACP-compatible agent (Claude Code,
Codex, Gemini CLI, GitHub Copilot CLI) works in any ACP-compatible editor via
one JSON-RPC schema [zed.dev/acp](https://zed.dev/acp). It's scoped to
editors, not arbitrary sources, but its message schema is worth reading
before finalizing this project's own `Event`/`Response` wire shape.

---

## 3. "Agent gateways" (2026's hottest infra buzzword) — all outbound, not inbound

Every vendor now ships something branded "agent gateway" or "AI gateway."
Checked: **agentgateway.dev** [agentgateway.dev](https://agentgateway.dev/) /
[github.com/agentgateway/agentgateway](https://github.com/agentgateway/agentgateway)
(Linux Foundation, donated by Solo.io — [linuxfoundation.org press
release](https://www.linuxfoundation.org/press/linux-foundation-welcomes-agentgateway-project-to-accelerate-ai-agent-adoption-while-maintaining-security-observability-and-governance)
— the most sophisticated OSS entrant), **Kong AI/Agent Gateway**
[konghq.com](https://konghq.com/solutions/agent-gateway), **Databricks Unity AI
Gateway** [databricks.com](https://www.databricks.com/blog/ai-gateway-governance-layer-agentic-ai),
**Google Cloud Agent Gateway** (part of Gemini Enterprise Agent Platform)
[cloud.google.com/blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform),
**Microsoft AI Gateway / Agent 365**
[learn.microsoft.com](https://learn.microsoft.com/en-us/microsoft-agent-365/overview),
**AWS Bedrock AgentCore Gateway**
[docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html),
**IBM mcp-context-forge**
[github.com/IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge),
**Microsoft mcp-gateway**
[github.com/microsoft/mcp-gateway](https://github.com/microsoft/mcp-gateway),
plus the LLM-provider-routing tier (**LiteLLM, Portkey, OpenRouter, Cloudflare
AI Gateway**).

**Every single one of these governs traffic an agent sends *outward*** — to
tools (MCP), to other agents (A2A), or to model providers (LLM APIs), confirmed
directly against each product's own docs (linked above). None ingest arbitrary
human/app-facing events (Slack messages, emails, GitHub webhooks, voice,
filesystem changes, cron ticks) and route them to a chosen agent backend, and
none have a pluggable *output-delivery* concept distinct from the tool-call
surface. GitHub's own topic taxonomy corroborates this split cleanly: the
[`mcp-gateway`](https://github.com/topics/mcp-gateway) and
[`ai-gateway`](https://github.com/topics/ai-gateway) topics are crowded with
outbound/tool-facing proxies (litellm, Kong, Portkey, agentgateway, and
~15 others, each independently confirmed outbound-only), while
[`agent-router`](https://github.com/topics/agent-router) — the topic that
would literally match this project's concept — carried exactly 4 tagged repos
at time of research, combined single-digit stars.

This is a genuine, evidence-backed gap, not an editorial claim: an entire
category of infrastructure has crystallized around "govern what the agent calls
out to," and essentially nothing exists for "decide what wakes the agent and
where the answer goes."

---

## 4. Single-vendor "channels" features — real signal, wrong shape

Three major vendors have shipped narrow versions of exactly this pattern, each
locked to their own backend:

- **Anthropic — Claude Code Channels / Routines** (research preview)
  [code.claude.com/docs/en/channels](https://code.claude.com/docs/en/channels),
  [code.claude.com/docs/en/routines](https://code.claude.com/docs/en/routines):
  an MCP server pushes Telegram/Discord/iMessage/webhook events into a
  *running Claude Code session*; Routines add schedule/API/GitHub-event
  triggers. Structurally the closest single-vendor analog to
  Source→Runtime→Output found anywhere. Anthropic's own Managed Agents
  engineering writeup states directly: *"This architecture is Claude-specific,
  not generic... does not support routing arbitrary external event sources to
  interchangeable model backends"*
  [anthropic.com/engineering/managed-agents](https://www.anthropic.com/engineering/managed-agents).
  Anthropic drew, in public, exactly the line this project is generalizing past.
- **Google — Gemini Enterprise Agent Platform "Agent Gateway."**
  [cloud.google.com/blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform)
  Governance/connectivity for agents-and-tools inside one GCP platform,
  Gemini-centric, closed SaaS, per-seat billing.
- **Microsoft — 365 Agents SDK**
  [learn.microsoft.com/microsoft-365/agents-sdk](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agents-sdk-overview),
  [github.com/microsoft/agents](https://github.com/microsoft/agents). The
  single closest *philosophical* match in the entire survey. Its own docs read
  almost like this project's vision statement: "Think of it as the plumbing
  layer between a user sending a message... and whatever logic you built to
  respond," and it explicitly disclaims being "an AI model, an orchestration
  engine, or a no-code builder." It is open source (MIT) and AI-agnostic by
  design. But it is a developer SDK you write handlers into (not a
  configure-and-run runtime), its channel list is Microsoft-centric (Teams/M365
  natively; Slack only via bolt-on integrations), production deployment for
  most channels needs Azure Bot Service registration, and it has no
  CLI/filesystem/scheduler/voice Source taxonomy. It's the best evidence that
  this project's *philosophy* is sound — just not yet available outside
  Microsoft's ecosystem, in Python, with zero cloud coupling.

## 5. Infra primitives — right job, wrong installation footprint

**Airflow, Celery, Temporal, NATS, Redis Pub/Sub** all have a real structural
analog to routing (task routing keys, subject-based pub/sub, request-reply).
All five, without exception, require standing up a separate server, broker, or
database before the first message can move — the opposite of "pip install and
done." Their own 2025–2026 AI pivots (Airflow's official `common-ai` provider,
April 2026; Temporal's OpenAI/Vercel/Google-ADK plugins culminating in a
dedicated "AI Partner Ecosystem," May 2026) *add* orchestration weight rather
than shipping a lightweight source-routing layer — further evidence that the
heavy-infra camp is solving "durable agent orchestration," not "wake the right
agent and get the answer back out," which is a lighter, different problem.
One genuinely validating data point: **Synadia Agents** (May 2026, built on
NATS) solves almost exactly this project's problem — route work to an
interchangeable agent, stream a response, track a session — but as a bolt-on
protocol requiring an external NATS server, not a zero-service embedded
library. **FastAPI**, by contrast, is not a competitor at all — it's a
philosophy reference (see below).

## 6. Closest real analogs — validate the idea, none of them qualify

- **cc-connect** [github.com/chenhg5/cc-connect](https://github.com/chenhg5/cc-connect)
  (Go, MIT): bridges ~12 coding-agent CLIs (Claude Code, Codex, Gemini CLI,
  Copilot, etc.) to 13 chat platforms, with a cron scheduler and decoupled
  input/output. The single most architecturally complete match found in this
  entire survey — and it's in Go, scoped to local coding-agent CLIs
  specifically, and heavier than "Flask, not Airflow" (built-in memory,
  multi-agent group chat).
- **Hermes Agent** [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
  (Python, MIT): a genuinely decoupled multi-channel gateway
  (Telegram/Discord/Slack/WhatsApp/Signal/email/webhook) with a swappable model
  provider. Fails on two axes this project cares about: only the *model* is
  swappable (not the whole agent/backend product), and it bakes in persistent
  memory and self-improving skills — both explicit non-goals here.
- **OpenClaw** [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw)
  (TypeScript): same shape as Hermes, wrong language, same
  model-swap-not-agent-swap limitation.
- **AgentBus** [github.com/Kanevry/agentbus](https://github.com/Kanevry/agentbus):
  "Webhooks in. Agent actions out." — the closest *named* match to this
  project's own mental model, but pre-alpha (2 GitHub stars, 4 commits at time
  of research, confirmed via the GitHub API), webhook-only sources, no
  output-delivery axis at all, and a commercial tier gating the interesting
  parts.

None of these disqualify this project. Collectively they say: *the pattern is
right, multiple independent teams have converged on wanting it, and nobody has
shipped it as a small, Python, zero-infra, genuinely-interchangeable-backend
library.*

---

## 7. Philosophy references (not competitors)

**FastAPI, Flask, Requests, Click.** Not prior art for the routing problem —
prior art for the *developer experience bar*. Ideas worth stealing directly:
FastAPI's type-hint-driven validation and automatic docs generation;
`@app.get(...)`-style decorator ergonomics for registering handlers; Click's
composable command groups for the CLI; Requests' "it just works, no config
object" session/adapter model. If Waken's API doesn't feel this obvious, it has
failed regardless of how correct the architecture is.

---

## Why this project deserves to exist

Three independent lines of evidence converge:

1. **The gap is real and specifically shaped.** Every agent framework
   (LangGraph/CrewAI/AutoGen/OpenAI Agents SDK) orchestrates *within* a run
   already started by *some* caller; every 2026 "agent gateway"
   (agentgateway.dev, Kong, Databricks, Google, Microsoft, AWS) governs what an
   agent calls *outward*; MCP and A2A standardize agent→tool and agent→agent,
   respectively, and both explicitly disclaim the human/app-facing Source side.
   Nothing standardizes *what wakes the agent and where the answer goes*.
2. **The market has already validated demand, piecemeal, at every altitude.**
   Anthropic (Channels/Routines), Microsoft (365 Agents SDK), and a half-dozen
   small OSS projects (cc-connect, Hermes, OpenClaw, AgentBus, Synadia Agents)
   have all independently built partial versions of this pattern in the last
   twelve months. None ship it as a small, self-hostable, genuinely
   backend-agnostic Python library — each is either vendor-locked, wrong
   ecosystem, missing an axis (Source diversity, Target interchangeability, or
   Output delivery), or scoped far heavier than a router needs to be.
3. **The honest risk, stated plainly:** this is now a crowded, fast-moving
   category, and several of the players circling it (Anthropic, Google,
   Microsoft, GitHub) have the resources to ship a lightweight, open version of
   exactly this at any time. That's a real threat to relevance, not a reason
   not to build — Flask, Requests, and Click all shipped into landscapes where
   "big companies already do this, heavily," and won on being small, obvious,
   and owned by no vendor. That's the bet here too: not a better agent
   framework, and not a bigger gateway — the thin, boring, vendor-neutral layer
   underneath both.
