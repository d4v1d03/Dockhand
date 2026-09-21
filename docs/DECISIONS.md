# Decisions

Architecture decision records: what was chosen, the alternatives, and the
consequences. Newest at the bottom.

---

## ADR-001 · FastAPI + Celery + Redis

**Context.** The agent loop is long-running (minutes), does blocking I/O
(LLM calls, `docker exec`), and must be cancellable; HTTP handlers must stay
responsive.

**Decision.** FastAPI for HTTP; Celery workers on a Redis broker for runs;
Redis also carries the live event stream and cancel flags.

**Alternatives.** (a) `asyncio.create_task` inside the web process — simplest,
but a web restart kills every run and there's no isolation between HTTP and
agent work. (b) `arq`/`dramatiq`/`rq` — lighter than Celery, but Celery
has beat scheduling built in and is the more common choice. (c) A
dedicated agent service with its own queue — overkill at this size.

**Consequences.** Two processes to run in dev. Worker code is synchronous
(Celery tasks are sync), so the `docker` and `openai` SDKs are used in their
sync forms — which is actually simpler. Clear seam: `web` never imports
`sandbox/` or `llm/`.

---

## ADR-002 · Server-rendered HTML + vanilla JS, no SPA

**Context.** UI needs: a form, a list, and one live-updating timeline.

**Decision.** Jinja2 templates, one CSS file, one `session.js` using
`EventSource`. No bundler, no framework.

**Alternatives.** React/Vite — nicer component model but adds a toolchain and
a second language surface; HTMX — attractive, but SSE-driven DOM patching of
a timeline is easier to reason about in ~200 lines of plain JS.

**Consequences.** Zero build step; the whole UI is readable in one sitting.
If the timeline grows complex (streaming deltas, xterm), revisit.

---

## ADR-003 · One OpenAI-compatible client for all providers

**Context.** Primary targets are Chinese models (DeepSeek, Qwen, Kimi, GLM,
MiniMax). Every one of them exposes an OpenAI-compatible chat endpoint with
`tools`/`tool_calls`; OpenRouter fronts all of them with one key.

**Decision.** Use the official `openai` Python SDK with `base_url`, `api_key`
and `model` from config. Wrap it in a small `LLMClient` that normalises the
response into `AssistantTurn` and records usage.

**Alternatives.** Per-provider SDKs (DashScope SDK, etc.) — more features,
more surface, no benefit for chat+tools. LiteLLM — does the same
normalisation, but adds a layer between the loop and the API for no gain here.

**Consequences.** Switching models is an `.env` edit. Provider quirks
(`reasoning_content`, differing `finish_reason`s, rate-limit headers) are
handled in one file and documented in Field notes.

---

## ADR-004 · Non-streaming LLM calls

**Context.** Streaming tool-call arguments over SSE from OpenAI-compatible
providers is fiddly (partial JSON, provider differences) and adds little:
what users want to watch is *commands and their output*, not tokens.

**Decision.** `chat()` is a single blocking request. Liveness comes from
tool-call/tool-result events.

**Alternatives.** Stream from day one — better final-message UX, higher
complexity in the loop itself, for little user-visible gain.

**Consequences.** A visible pause of 5–30 s while the model thinks; the UI
shows a "thinking…" state. Streaming assistant text is a later addition.

---

## ADR-005 · Server-Sent Events, not WebSockets

**Context.** Live updates flow strictly server → browser. The only
client → server messages (new task, follow-up, stop) are ordinary POSTs.

**Decision.** SSE via `sse-starlette`, with `id:` on every frame so the
browser's automatic reconnect sends `Last-Event-ID`.

**Alternatives.** WebSockets — bidirectional, but that's unneeded, and you
give up free reconnection/replay semantics and plain-HTTP debuggability
(`curl -N`).

**Consequences.** Proxies need keepalives (sent every 15 s). One SSE
connection per open session tab — fine for a single-user tool.

---

## ADR-006 · Redis Streams + SQLite for events (not pub/sub alone)

**Context.** The SSE endpoint must (a) replay history on connect/reconnect
and (b) tail new events with no gap between the two. Redis pub/sub is
fire-and-forget: anything published between "read history" and "subscribe"
is lost.

**Decision.** `publish()` writes the event to SQLite (durable, the source of
truth) then `XADD`s it to `session:{id}:events` (`MAXLEN ~1000`). The SSE
handler replays from SQLite `> Last-Event-ID`, then `XREAD BLOCK`s from the
same id. Stream entries carry the SQLite `event.id` so the two are aligned.

**Alternatives.** Pub/sub + DB replay — the race above. Poll SQLite every
500 ms — works, but wasteful. Kafka/NATS.

**Consequences.** Two writes per event (cheap). If Redis loses the stream
(restart, trim), replay from SQLite still works.

---

## ADR-007 · Separate `messages` (transcript) and `events` (timeline)

**Context.** Tempting to store one list and derive both.

**Decision.** Two tables. `messages` is exactly what the LLM API consumes.
`events` is what the UI consumes, with metadata the model never sees.

**Alternatives.** One table with a `kind` column — every consumer then
filters and maps, and the transcript shape (tool-call ids, roles) gets
polluted by UI concerns.

**Consequences.** A tool call is written twice (as an assistant message
and as an event) — deliberate. Follow-ups resume from `messages`; page
loads render from `events`.

---

## ADR-008 · Sibling containers via the Docker socket; `sleep infinity` + `exec`

**Context.** The worker must create/destroy sandboxes. In compose the worker
is itself a container.

**Decision.** Mount `/var/run/docker.sock` into the worker; sandboxes are
*sibling* containers on the host daemon (not docker-in-docker). Each
sandbox starts `sleep infinity` as PID 1; every tool call is a
`docker exec`.

**Alternatives.** Docker-in-Docker (privileged, slow, nested daemon).
One container per command (`docker run` each time) — loses state between
calls and pays startup cost 40× per run. SSH into a long-lived VM — heavier
to provision, but the right answer at scale.

**Consequences.** The worker is root-equivalent on the host — documented,
acceptable for a local dev tool, and the reason `Sandbox` is an interface
you could back with a remote daemon or gVisor later.

---

## ADR-009 · Explicit file tools alongside `bash`

**Context.** A model with only `bash` can do everything, in theory.

**Decision.** Provide `read_file`, `write_file`, `edit_file` (unique-match
string replace), `list_files`, `search` in addition to `bash`.

**Alternatives.** `bash` only — fewer tools to write, but models make many
more quoting/heredoc mistakes, outputs are unstructured, and the UI can't
show "edited `app.py`". Full patch-apply tool (`apply_patch`) — powerful,
but models produce malformed hunks often enough to frustrate.

**Consequences.** ~150 more lines of tool code; markedly higher success
rate and a far better trace. `edit_file` errors are written for the model
("`old` found 3 times; include more context") — that phrasing matters.

---

## ADR-010 · `finish` and `ask_user` are tools

**Context.** How does a run end? "The model stopped emitting tool calls" is
ambiguous — it may be summarising mid-task.

**Decision.** Two terminal tools. `finish(summary)` ends the run as
`completed`; `ask_user(question)` ends it as `waiting_for_user`. A turn with
text and no tool calls is treated as `completed` too (models sometimes
forget), but the prompt asks for `finish`.

**Alternatives.** Parse the assistant text for "DONE" markers — brittle.

**Consequences.** The state machine is explicit and testable; the UI can
render the final summary distinctly.

---

## ADR-011 · SQLite, not Postgres

**Context.** Single user, one machine, three small tables.

**Decision.** SQLite file under `data/`, via SQLAlchemy so the swap is a URL
change.

**Alternatives.** Postgres in compose — one more container and migrations
for no gain at this size.

**Consequences.** `web` and `worker` share the file (fine with WAL mode).
Multi-writer contention is not a concern at one run at a time.

---

## ADR-012 · Timeouts via the container's `timeout`, not from outside

**Context.** `exec_run` blocks with no timeout parameter; cancelling an exec
from the API is awkward and leaves zombie processes.

**Decision.** Wrap every command: `timeout -k 5 <n>s bash -lc '<cmd>'`.
Exit code 124 → `timed_out=True`.

**Alternatives.** Run `exec_run` in a thread and abandon it on timeout —
leaks the process inside the container. Kill the container — loses state.

**Consequences.** Timeouts are reliable and cheap. A `Stop` during a long
command waits for that command's timeout (max 600 s); acceptable for now,
noted in ARCHITECTURE §10.

---

## ADR-013 · Keep sandboxes alive after a run; reap by TTL

**Context.** Follow-ups should be instant and keep the agent's changes.

**Decision.** Container stays up after `completed`/`waiting_for_user`; a
beat task removes containers older than `SANDBOX_TTL_MINUTES`. A follow-up
on a reaped session recreates and re-clones, with a warning event.

**Alternatives.** Destroy on finish (loses work, slow follow-ups);
keep forever (disk/CPU leak).

**Consequences.** Users can lose unsaved changes after the TTL — the diff
panel makes "download the patch" obvious. Re-applying the last patch
automatically is a later addition.

---

## ADR-014 · `uv` for dependency management

**Context.** Need reproducible installs and a lockfile; Python 3.14 on the
dev machine may lack wheels for some packages.

**Decision.** `uv` with `pyproject.toml` + `uv.lock`, `requires-python =
">=3.12"`. `uv` can fetch a managed 3.12/3.13 if 3.14 causes trouble.

**Alternatives.** `venv` + `requirements.txt` (like fleetwatch) — works,
no lockfile; Poetry — slower, heavier.

**Consequences.** One-line install for `uv`; `uv run` everywhere in the
docs. `pip install -e .` still works for anyone without `uv`.

---

---

## ADR-015 · The patch is stored on the session when a run ends

**Context.** The workspace lives in a container that is reaped after a TTL;
the result of a session must not disappear with it.

**Decision.** At the end of every run the worker computes `git diff` and
`--numstat` and stores both on the session row. The diff endpoint serves the
live diff while the container exists and the stored one afterwards, and says
which. A `.patch` download is the way results leave the system.

**Alternatives.** Push a branch from the sandbox — needs credentials inside
the container, which the design forbids. Keep containers forever — a leak.

**Consequences.** One more `git diff` per run (milliseconds). Results are
durable; workspaces stay disposable.

---

## ADR-016 · A scripted demo model behind the same interface

**Context.** Developing the UI, running the compose stack, and load-testing
should not require an API key or spend tokens.

**Decision.** `LLM_BASE_URL=fake` selects `DemoLLM`, which replays a short
plausible script (orient, write, test, finish; ask on request; answer
follow-ups) through the real tool registry against a real sandbox, and
writes traces like the real client.

**Alternatives.** Mock at the HTTP layer — brittle across providers; skip
and always use a real key — slow, costly, rate-limited.

**Consequences.** The whole stack runs end to end in seconds with no
credentials, and tests of the runner and UI have a deterministic model.

---

## ADR-017 · Provider quirks are absorbed in one place

**Context.** OpenAI-compatible providers differ in details: where cached
token counts live, `reasoning_content` on thinking models, Gemini's
`thought_signature` that must be echoed back on every tool call, per-minute
and per-day quota errors.

**Decision.** `parse_response` normalises every response into
`AssistantTurn`; unknown fields on tool calls are kept on `ToolCall.extra`
and re-emitted by `to_message()`; rate-limit handling lives in the client.
Nothing outside `llm/` knows which provider is in use.

**Consequences.** Adding a provider is a change to one file. Transcripts
stored in the database carry the extras, so follow-ups remain valid across
providers that require them.
