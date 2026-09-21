# Dockhand

A self-hosted AI coding agent. Give it a task and, optionally, a git repo. It spins
up an isolated Docker sandbox, writes code, runs the tests, iterates on failures,
and streams every command it runs back to you — until the job is done or you
tell it to stop.

Built from scratch, without an agent framework, to keep the whole loop visible:
one file is the agent, one file is the sandbox boundary, one file is the LLM
client. Works with any OpenAI-compatible provider (DeepSeek, Qwen, Kimi, GLM,
Gemini, OpenRouter, …).

## What it does

| | |
| --- | --- |
| **Task in, code out** | Describe a task in plain English. Point at a public git URL or start from an empty workspace. |
| **Real sandbox** | Every session gets a fresh container: non-root, all Linux capabilities dropped, memory/CPU/pid limits, no host mounts, no secrets inside. |
| **Agent loop with tools** | `bash`, `read_file`, `write_file`, `edit_file`, `list_files`, `search`, `ask_user`, `finish`. The model plans, acts, reads the result, and iterates — the same ReAct-style loop every coding agent uses. |
| **Live trace** | Every model turn, tool call and command output is an event; the CLI prints them as they happen, the web UI streams them over SSE. |
| **Traces & usage** | Every LLM call is logged as JSONL with the exact request, response, tokens, cached tokens and latency. |
| **Diff & patch** | See exactly what changed (`git diff`, build artefacts excluded) and take it as a patch. |

## How a run works

```
task ──▶ system prompt (env facts + workspace tree + method) + user message
              │
              ▼
        ┌─ llm.chat(transcript, tool schemas) ──▶ model replies with tool calls
        │        │
        │        ▼
        │   registry.run(call, sandbox) ──▶ docker exec / tar in / tar out
        │        │
        │        ▼
        │   tool result appended to transcript, event emitted
        └────────┘  repeat until `finish`, `ask_user`, cancel, or max_steps
```

The model never runs anything itself — it only writes JSON asking for a tool.
Every side effect happens inside the container, under the worker's limits.
Every tool output is bounded (head + tail, with an omission marker) before it
enters the context window.

## Architecture

```
 Browser ──HTML/JSON──▶ ┌──────────────┐          ┌───────────────┐
   ▲                    │  web         │  enqueue │  worker        │
   │  SSE (live events) │  FastAPI +   │ ───────▶ │  Celery        │
   └────────────────────│  Jinja2      │          │                │
                        └──────┬───────┘          │  agent loop    │
                               │                  │   ├─ LLM call ─┼──▶ any OpenAI-compatible API
                        ┌──────▼───────┐  events  │   └─ tools ────┼──▶ ┌─────────────────────┐
                        │  Redis       │ ◀─────── │                │    │  sandbox container  │
                        │  broker +    │          └───────┬────────┘    │  /workspace (repo)  │
                        │  event stream│                  │ docker API  │  bash, git, py, node│
                        └──────────────┘                  └────────────▶│  non-root, limited  │
                        ┌──────────────┐                                └─────────────────────┘
                        │  SQLite      │  sessions · transcript · events
                        └──────────────┘
```

* `web` serves pages, the JSON API and the SSE stream. It never touches Docker or the LLM.
* `worker` runs one Celery task per agent run: creates the sandbox, drives the
  loop, publishes events. `acks_late` + resumable transcripts mean a crashed
  worker's run is picked up, not lost.
* Redis is the Celery broker and carries a per-session event stream that the
  SSE endpoint tails (replay via `Last-Event-ID`).
* SQLite holds sessions, the LLM transcript, and the event timeline.
* A Traefik reverse proxy fronts `web`, so `docker compose up --scale web=3`
  works unchanged.

## Sandbox guarantees

| Concern | Mitigation |
| --- | --- |
| Agent runs arbitrary code | One container per session; user `agent` (uid 1000); `--cap-drop ALL`; `no-new-privileges`; memory / CPU / pids limits; no host mounts |
| Runaway commands | Wrapped in the container's own `timeout` (default 120 s, max 600 s) |
| Runaway agent | `MAX_STEPS`; every limit surfaces as a clear error, never a hang |
| Context blow-up | Tool output capped and truncated head+tail; `read_file` paged at 400 lines |
| Secrets | The sandbox receives no API key and no host environment |
| Network exfiltration | `SANDBOX_NETWORK=none` turns the sandbox fully offline |
| Stray containers | Every container is labelled; `make clean-sandboxes` and a TTL reaper |

This is a single-user dev tool: the worker holds the Docker socket, which is
root-equivalent on the host. Don't expose it to the internet as-is.

## Quickstart

```bash
cp .env.example .env            # set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
make build-sandbox              # the image agents run in
docker compose up               # redis + traefik + web + worker → http://localhost:8088
```

No API key yet? `LLM_BASE_URL=fake` runs a scripted demo model against real
sandboxes, enough to try the UI end to end.

Run the agent from the terminal, no web stack needed:

```bash
docker compose up -d redis
uv sync
uv run python -m dockhand.agent.cli "Add a --version flag and a test for it" --repo https://github.com/you/repo
uv run python -m dockhand.agent.cli "Create a CSV→JSON CLI with pytest tests and make them pass"
```

Every run writes `data/traces/<run_id>.jsonl` — the exact prompt the model saw at
each step, its reply, tokens and latency.

## Configuration

| var | default | |
| --- | --- | --- |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | — | any OpenAI-compatible endpoint |
| `LLM_TEMPERATURE` | `0.2` | |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `DATABASE_URL` | `sqlite:///data/dockhand.db` | |
| `SANDBOX_IMAGE` | `dockhand-sandbox:latest` | |
| `SANDBOX_NETWORK` | `bridge` | `none` for offline |
| `SANDBOX_MEMORY` / `SANDBOX_CPUS` | `2g` / `2` | |
| `SANDBOX_TTL_MINUTES` | `60` | idle containers are reaped after this |
| `MAX_STEPS` | `40` | LLM calls per run |
| `MAX_TOOL_OUTPUT_CHARS` | `8000` | |
| `DEFAULT_TOOL_TIMEOUT_S` / `MAX_TOOL_TIMEOUT_S` | `120` / `600` | |
| `TRAEFIK_PORT` | `8088` | host port for the compose stack |

## Layout

```
dockhand/
├── config.py            settings
├── main.py              FastAPI app · web/ (pages, api, sse)
├── worker.py            Celery app · run_session · reap_sandboxes
├── db/                  SQLAlchemy engine · models
├── sandbox/             Sandbox (Docker) · FakeSandbox · SandboxProtocol
├── llm/                 OpenAI-compatible client · FakeLLM · trace writer
└── agent/               tools · prompts · loop (run_agent) · cli
sandbox/Dockerfile       the image agents run in
tests/unit               FakeLLM + FakeSandbox, no Docker needed
tests/integration        real containers (skipped when no daemon)
```

## Development

```bash
make test        # unit tests
make test-all    # + integration tests against real containers
make lint        # ruff
make web         # uvicorn with reload on :8000
make worker      # celery worker
```

## Docs

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — processes, session lifecycle, data model, streaming, agent loop, sandbox, HTTP surface.
* [docs/DECISIONS.md](docs/DECISIONS.md) — architecture decision records.
* [docs/ROADMAP.md](docs/ROADMAP.md) — what's done, what's next.

## License

MIT
