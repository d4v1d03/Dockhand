# Dockhand

> A self-hosted, from-scratch clone of Ona / Vorflux-style **AI coding agents**.
> Give it a task (and optionally a git repo). It spins up an isolated Docker
> sandbox, writes code, runs the tests, and streams every command it runs back
> to your browser — until the job is done or you tell it to stop.

Dockhand is a learning project: the goal is to understand, by building it, how
products like Ona, Vorflux, Devin, Codex-cloud and Claude Code (web) actually
work under the hood — the agent loop, tool calling, sandboxing, and streaming a
live trace to a UI. It is deliberately small, but every piece that matters in a
real product is here.

Work is done in numbered steps: an MVP (Steps 1–8), then **AI-engineering
labs** (evals, context engineering, routing, planner/verifier, guardrails,
retrieval, MCP, …) and **scale-out labs** (load balancing, worker pools,
caching, sharding). The core is scheduled as a **10-day track** (~45 h);
the remaining labs are a *later* menu. See **[docs/PLAN.md](docs/PLAN.md)**
for the schedule and **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for
how it fits together.

---

## What it does (MVP scope)

| Feature | Description |
| --- | --- |
| **Task in, code out** | Type a task in plain English. Optionally paste a public git URL — the agent works inside that repo. Or start from an empty workspace and let it scaffold. |
| **Real sandbox** | Every session gets a fresh Docker container with a shell, git, Python and Node. CPU / memory / process limits. Thrown away when done. |
| **Agent loop with tools** | The model plans, calls tools (`bash`, `read_file`, `write_file`, `edit_file`, `list_files`, `search`, `finish`), sees results, and iterates — the same ReAct-style loop every coding agent uses. |
| **Live trace** | Every thought, tool call, command and its output streams to the browser over Server-Sent Events, as it happens. |
| **Human in the loop** | Stop the agent at any time. Send follow-up messages. The agent can pause and ask *you* a question. |
| **Diff & patch** | See exactly what changed (`git diff`) and download it as a `.patch`. |
| **Any OpenAI-compatible model** | Primary targets are Chinese models — DeepSeek, Qwen, Kimi, GLM, MiniMax — via one config (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). OpenRouter works too. |
| **Usage tracking** | Tokens per LLM call, per session, shown in the UI. |

Not in scope (for now): auth/multi-user, GitHub PR creation, persistent
workspaces, hardware-isolated sandboxes. See *Stretch* in the plan.

---

## Architecture at a glance

```
 Browser ──HTML/JSON──▶ ┌──────────────┐          ┌───────────────┐
   ▲                    │  web         │  enqueue │  worker        │
   │  SSE (live events) │  FastAPI +   │ ───────▶ │  Celery        │
   └────────────────────│  Jinja2      │          │                │
                        └──────┬───────┘          │  agent loop    │
                               │                  │   ├─ LLM call ─┼──▶ DeepSeek / Qwen / Kimi …
                        ┌──────▼───────┐  events  │   └─ tools ────┼──▶ ┌─────────────────────┐
                        │  Redis       │ ◀─────── │                │    │  sandbox container  │
                        │  broker +    │          └───────┬────────┘    │  /workspace (repo)  │
                        │  event stream│                  │ docker API  │  bash, git, py, node│
                        └──────────────┘                  └────────────▶│  non-root, limited  │
                        ┌──────────────┐                                └─────────────────────┘
                        │  SQLite      │  sessions · messages · events
                        └──────────────┘
```

* **web** — serves the pages, the JSON API and the SSE stream. Never talks to
  Docker or the LLM directly.
* **worker** — runs one `run_session` Celery task per agent run: creates the
  sandbox, drives the LLM ↔ tools loop, publishes events.
* **Redis** — Celery broker *and* a per-session event stream that the SSE
  endpoint tails.
* **SQLite** — durable record of sessions, the LLM transcript, and the event
  timeline (so a page reload or a follow-up message can pick up where it left off).
* **sandbox** — one throwaway container per session, built from
  `sandbox/Dockerfile`. All tools execute inside it.

---

## Status

| Step | What | 10-day track | Status |
| --- | --- | --- | --- |
| 0 | Plan & documentation | — | ✅ done |
| 1 | Project skeleton: FastAPI, Celery, Redis, Traefik, compose, sandbox image | Day 1 | ✅ |
| 2 | Sandbox manager (Docker SDK): create / exec / read / write / destroy | Day 2 | ✅ |
| 3 | LLM client + tools + agent loop + trace log (CLI, no web yet) | Days 3–4 | 🔨 in progress |
| 4 | **Eval harness & trace viewer** — the number every later change is judged by | Day 4 | ⬜ |
| 5 | Persistence, Celery task, event bus, SSE endpoint | Day 5 | ⬜ |
| 6 | Web UI: new task, live session trace, per-step prompt view, stop | Day 6 | ⬜ |
| 7 | Multi-turn, `ask_user`, diff & patch download | Day 7 | ⬜ |
| 8 | Hardening essentials: reaper, limits, `compose up`, tests — **MVP complete** | Day 7 | ⬜ |
| 9 | **AI-engineering labs** — 9.1 context engineering & prompt caching · 9.3 routing, structured outputs, reasoning models · 9.5 planner & verifier | Days 8–10 | ⬜ |
| 9 | *later:* 9.4 guardrails · 9.2 retrieval (embeddings vs grep) · 9.6 MCP · 9.8 sub-agents · 9.7 fine-tuning (short) | later | ⬜ |
| 10 | **Scale-out labs** — 10.2 load-balanced `web` · 10.3 worker pool & crash recovery | Days 9–10 | ⬜ |
| 10 | *later:* 10.1 metrics · 10.5 caching · 10.4 rate limiting · 10.6–10.8 MinIO, Postgres, sharding | later | ⬜ |

---

## Quickstart

*(Lands in Step 1. Target developer experience:)*

```bash
cp .env.example .env            # add LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
docker build -t dockhand-sandbox sandbox/
docker compose up               # redis + web + worker
# open http://localhost:8088   (dev without compose: :8000)
```

For day-to-day development you'll run Redis in Docker and `web` / `worker`
directly with `uv run` so reloads are instant. Details in the plan.

---

## Docs

* [docs/PLAN.md](docs/PLAN.md) — step-by-step build plan, the concepts map
  (what a founding AI engineer should be able to explain), definition of
  done per step, the AI-engineering and scale-out labs.
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, data model, agent
  loop, event types, sandbox design, security.
* [docs/DECISIONS.md](docs/DECISIONS.md) — why FastAPI + Celery, why SSE, why
  Redis Streams, why OpenAI-compatible, etc.

## License

MIT
