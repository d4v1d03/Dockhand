# Build plan

Dockhand is built in three tracks:

* **Steps 0–8 — the MVP.** A working product: task → sandbox → agent → live trace → diff.
* **Step 9 — AI-engineering labs.** The primary learning track: what a founding
  engineer at an AI startup is expected to know, each lab measured against the
  eval harness from Step 4.
* **Step 10 — Scale-out labs.** Practical system design: load balancers,
  worker pools, caching, rate limiting, object storage, Postgres, sharding.

Each step ends with something you can **run and show**, builds on the previous
one, and is sized for one focused session.

---

## Time budget: the 10-day track

**Constraint:** 10 days × 4–5 h ≈ 45 h. Decent developer, little prior AI
experience. Claude Code does most of the typing; you read every line, run
every Definition of done, and hand-write the pieces marked **✍️ you write**.

**What fits:** the whole MVP (Steps 1–8, ~34 h) plus **three AI labs and two
scale labs** (~12 h). Everything else is a *Later* menu — still in this doc,
still worth doing, just not in the 10 days. There is no slack in this
schedule; if a day slips, drop Day 10's labs first, then Day 9's.

| Day | Do | Hours | You should be able to explain afterwards |
| --- | --- | --- | --- |
| 1 | **Step 1** skeleton (FastAPI, Celery, Redis, Traefik, compose, sandbox image) | 4 | processes, broker/worker, what `docker.sock` grants |
| 2 | **Step 2** sandbox manager | 4 | `docker exec`, tar file transfer, cgroup limits, in-container timeouts |
| 3 | **Step 3** LLM client + tools + agent loop, part 1 (client, tools, ✍️ loop) | 5 | tool calling end to end; the ReAct loop; truncation |
| 4 | **Step 3** part 2 (✍️ system prompt, CLI, two real models) + **Step 4** evals & traces | 5 | evals & variance; reading a trace to explain a failure |
| 5 | **Step 5** persistence, Celery task, event bus, ✍️ SSE | 5 | locks/idempotency, Redis Streams, SSE + `Last-Event-ID` |
| 6 | **Step 6** web UI with per-step prompt view | 5 | rendering agent traces; progressive enhancement |
| 7 | **Step 7** multi-turn, `ask_user`, diff/patch + **Step 8** essentials (reaper, limits, `compose up`) | 5 | human-in-the-loop as a state machine; agent ops |
| 8 | **Lab 9.1** context engineering & prompt caching (✍️ compaction) | 4 | what goes in the window; cached-token economics |
| 9 | **Lab 9.3** routing / structured outputs / reasoning models + **Lab 10.2** scale `web` behind Traefik | 5 | cost as a design constraint; stateless tiers |
| 10 | **Lab 9.5** planner & verifier (✍️ verifier prompt) + **Lab 10.3** worker pool & crash recovery + 1 h demo prep | 5 | LLM-as-judge and whether it helps; at-least-once delivery |

**Later menu** (after day 10, in rough order of value): 9.0 framework
comparison (1 h), 9.4 guardrails, 9.2 retrieval, 9.6 MCP, 9.8 sub-agents,
9.7 fine-tuning (short), 10.1 metrics, 10.5 caching, 10.4 rate limiting,
10.6–10.8 storage/Postgres/sharding.

### Working mode

* **Claude scaffolds, you own the core.** Pieces marked **✍️ you write** are
  written by you first (Claude reviews, you fix): the agent loop, the system
  prompt, one tool (`edit_file`), the SSE generator, the compaction function,
  the verifier prompt. That's where the understanding sticks.
* **Read before run.** Every file Claude writes, you read fully before running
  the Definition of done. If you can't explain a line, ask before moving on.
* **Field notes daily.** Two lines a day in `docs/DECISIONS.md` → Field
  notes: what the model did that surprised you, what you changed.
* **Measure.** From Day 4 on, every change to prompts, tools or models gets an
  eval run before and after.

Rules of the road

* One step per sitting. Finish it, run its *Definition of done*, commit, then stop.
* Keep scope. Anything tempting that isn't in the step goes to *Later* or
  [Stretch](#stretch).
* When code and docs disagree, fix the docs in the same commit.

---

## Concepts map — what a founding AI engineer should be able to explain

Use this as a self-check. Each row says where in the project you meet the idea
hands-on.

### Core agent engineering

| Concept | Where | You should be able to explain… |
| --- | --- | --- |
| Tool / function calling | Step 3 | schema → call → result → next turn; why every `tool_call_id` needs a reply; what makes a tool description good |
| Agent loop (ReAct) | Step 3 | observe → think → act; stop conditions; why `finish` is a tool; max-steps as a safety net |
| System-prompt design | Step 3 | method > rules; what facts to inject (env, repo tree); how prompt wording changes behaviour (measured in Step 4) |
| Tool-output truncation | Step 3 | why it's non-negotiable; head+tail; the model must be told output was cut |
| Provider abstraction & quirks | Step 3 | the OpenAI-compatible surface; `reasoning_content`; finish reasons; rate limits; how DeepSeek vs Qwen vs Kimi differ in practice |
| **Evals** | **Step 4** | task suites with hidden checks; pass@1 vs pass@k; variance across trials; why one run proves nothing; cost per solved task |
| **Tracing / LLM observability** | **Step 4, 6** | the exact request per step; latency and tokens per call; how to debug "why did it do that" |
| Human-in-the-loop | Step 7 | `waiting_for_user` / `waiting_for_approval` as first-class states |
| Failure modes of agents | Step 8 + everywhere | loops, hallucinated paths, giant outputs, flaky tools — and the guard for each |

### AI-engineering labs (Step 9)

| Concept | Lab | You should be able to explain… |
| --- | --- | --- |
| Context engineering & compaction | 9.1 | what goes in the window and why; summarising old turns; scratchpad files as external memory |
| Prompt caching economics | 9.1 | stable-prefix prompts; cached vs uncached token prices; measuring hit rate |
| Retrieval for code (embeddings vs lexical) | 9.2 | chunking, embedding, vector search; when `rg` beats embeddings and vice versa; why several coding agents dropped embeddings |
| Model routing & cost | 9.3 | cheap model for cheap jobs; fallback providers; cost per session as a design constraint |
| Structured outputs | 9.3 | JSON-schema constrained responses; when to use them instead of tool calls |
| Reasoning ("thinking") models | 9.3 | when extended reasoning helps (planning) and hurts (tool-heavy loops); cost/latency trade-off |
| Guardrails & permission modes | 9.4 | rules + classifier for risky actions; approval gates; allowlists |
| Planning, verification, self-correction | 9.5 | plan-then-execute; LLM-as-judge; verifier loops; measuring whether they actually help |
| Agent frameworks (LangGraph etc.) vs hand-rolled | 9.0 *later* | what the abstractions wrap; when a framework helps and when the loop *is* the product |
| MCP (Model Context Protocol) | 9.6 | what an MCP server/client is; dynamic tool discovery; why it became the standard |
| Fine-tuning (light) | 9.7 *later* | what LoRA is; SFT chat format; when to fine-tune vs prompt vs RAG |
| Multi-agent / sub-agents | 9.8 | context isolation; delegation; parallel tool execution; when it's worth it |

### System design (Step 10)

| Concept | Lab | You should be able to explain… |
| --- | --- | --- |
| Stateless tiers & load balancing | 10.2 | why SSE across replicas works (state in Redis); health checks; when you'd need sticky sessions |
| Queues, worker pools, at-least-once | 10.3 | `acks_late`, prefetch, visibility timeout; idempotent tasks; crash recovery |
| Rate limiting & backpressure | 10.4 | token bucket; distributed semaphore; degrading gracefully |
| Caching | 10.5 | cache-aside vs write-through; TTL vs invalidation; measuring hit rate |
| Blob storage | 10.6 | why patches/logs don't belong in a relational DB; presigned URLs |
| Relational at scale | 10.7–10.8 | migrations; pooling; when to shard and what to do first instead |

---

## Step 0 — Plan & documentation ✅

Deliverables: this file, `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, git repo initialised.

---

## Step 1 — Project skeleton & infrastructure

Goal: every process exists and talks to its neighbours, with zero product logic.

**Build**

* `pyproject.toml` (managed with `uv`): `fastapi`, `uvicorn[standard]`,
  `jinja2`, `python-multipart`, `celery[redis]`, `redis`, `docker`,
  `sqlalchemy`, `pydantic-settings`, `openai`, `sse-starlette`, `pyyaml`;
  dev: `pytest`, `httpx`, `ruff`.
* `dockhand/config.py` — `Settings` per ARCHITECTURE §11; `.env.example`.
* `dockhand/main.py` — FastAPI app; `GET /health` → `{ok, redis, db}`;
  static + templates wired; `templates/base.html` with header, CSS
  variables, responsive shell; `/` renders an empty "New task" page.
* `dockhand/worker.py` — Celery app on Redis; a `ping` task; beat schedule
  placeholder.
* `docker-compose.yml` — `redis`, `traefik` (fronts `web` via labels, so
  `--scale web=3` in Step 10 needs no changes), `web`, `worker` (mounts
  `/var/run/docker.sock`); app `Dockerfile`.
* `sandbox/Dockerfile` — Debian slim + git, curl, ripgrep, build-essential,
  python3/pip/venv, Node LTS; user `agent`; `/workspace`; `sleep infinity`.
* `Makefile` — `dev-redis`, `web`, `worker`, `build-sandbox`, `test`, `lint`,
  `clean-sandboxes`.

**Definition of done**

```bash
docker compose up -d redis
uv run uvicorn dockhand.main:app --reload      # http://localhost:8000/health → {"ok":true,"redis":true,"db":true}
uv run celery -A dockhand.worker worker -l info # picks up a ping task sent from a python shell
docker build -t dockhand-sandbox sandbox/ && docker run --rm dockhand-sandbox bash -c 'python3 --version && node --version && rg --version'
docker compose up                              # same /health via http://localhost:8088 (through traefik)
```

**What you learn**: FastAPI app structure, Celery + Redis basics, Docker
images vs containers, `docker.sock` and what mounting it means, a reverse
proxy in front of an app, `uv`.

---

## Step 2 — Sandbox manager

Goal: a `Sandbox` object that can create a container, run commands with a
timeout, read/write files, produce a diff, and destroy itself. No LLM yet.

**Build**

* `dockhand/sandbox/manager.py` per ARCHITECTURE §8: `create`, `attach`,
  `exec`, `read_file`, `write_file`, `diff`, `is_alive`, `destroy`.
  Labels, limits, `cap-drop`, non-root, optional `network=none`.
* Repo cloning (`--depth 50`) or `git init`; git identity configured.
* `exec` wraps the command in `timeout -k 5 <n>` inside the container;
  merges stdout/stderr; returns `ExecResult(exit_code, output, duration_ms, timed_out)`.
* `read_file`/`write_file` over `get_archive`/`put_archive` (tar), parent
  dirs created.
* `FakeSandbox` (in-memory filesystem + scripted command results) for unit
  tests and token-free load tests later.
* `python -m dockhand.sandbox --repo <url> "ls -la && git log -1"`
  demo entrypoint.

**Definition of done**

```bash
uv run python -m dockhand.sandbox --repo https://github.com/pallets/flask "git log --oneline -3 && python3 -c 'print(42)'"
uv run pytest tests/integration -m docker      # create → exec → write → read → diff → destroy; timeout test; non-root test
docker ps -a --filter label=dockhand.session   # empty after tests
```

**What you learn**: the Docker Engine API from Python, what `exec` really
does, tar-based file transfer, cgroup limits, capability dropping, why
`timeout` inside beats killing from outside.

---

## Step 3 — LLM client, tools, agent loop (CLI only)

Goal: the agent works end-to-end from the terminal. Highest learning density
in the project — take your time.

**Build**

* `dockhand/llm/types.py` + `client.py` — `LLMClient.chat(messages, tools)`
  over the `openai` SDK with `base_url`; retries; usage + latency;
  `reasoning_content` passthrough; `FakeLLM` (scripted turns) for tests.
* **Trace log** — every LLM call appends one JSON line to
  `data/traces/<run_id>.jsonl`: step, full request (messages, tools),
  response, usage, latency, model. This is the raw material for Step 4.
* `dockhand/agent/tools.py` — `Tool` base, `ToolRegistry`, the eight tools
  from ARCHITECTURE §6 with JSON schemas and descriptive error strings.
  ✍️ You write `edit_file` (the unique-match replace + the error messages the
  model will read).
* ✍️ `dockhand/agent/prompts.py` — **you write the system prompt.** Builder
  injects workspace facts + method + constraints. Keep prompts in versioned
  files, not f-strings buried in code — you'll be diffing them in Step 4.
* ✍️ `dockhand/agent/loop.py` — **you write this one.** `run_agent(...)`
  exactly as ARCHITECTURE §5: cancel checks, per-call truncation,
  `finish`/`ask_user` handling, max steps, every `tool_call_id` answered.
  Claude reviews.
* `dockhand/agent/cli.py` — `uv run python -m dockhand.agent.cli "task"
  [--repo URL] [--keep]`; prints events colour-coded; prints the diff at the end.

**Definition of done**

```bash
uv run python -m dockhand.agent.cli "Create a Python CLI that converts CSV to JSON, with pytest tests, and make sure the tests pass."
uv run python -m dockhand.agent.cli --repo https://github.com/<you>/<small-repo> "Add a --version flag and a test for it."
uv run pytest tests/unit          # FakeLLM+FakeSandbox: tool order, truncation, dangling-call safety, max-steps, cancel
```

Success = the agent explores, edits, runs tests, iterates on failures, and
calls `finish` with an accurate summary, on at least one real Chinese model.
Try two models (e.g. DeepSeek and Qwen/Kimi) and write what differed into
Field notes.

**What you learn**: function calling end to end; how a model decides to use
a tool; ReAct; truncation; prompt structure; provider quirks.

---

## Step 4 — Eval harness & trace viewer (CLI)

Goal: a number that tells you whether a change made the agent better or
worse. Every later step reports it. This is the step that separates "I
built an agent" from "I engineer agents".

**Build**

* `evals/tasks/*.yaml` — 6–10 small tasks:
  ```yaml
  name: csv_to_json
  repo_url: null                      # or a small public repo
  prompt: "Write a CLI csv2json.py …"
  hidden:                             # copied into the sandbox AFTER the agent finishes
    tests/test_hidden.py: |
      …
  check: "python -m pytest -q tests/test_hidden.py"   # exit 0 = pass
  timeout_s: 600
  ```
  Mix: 3 empty-workspace, 3 existing-repo (bug fix, add feature, add
  test), 1–2 deliberately under-specified (should trigger `ask_user`).
* `evals/run.py` — runs each task `--trials N` times with the configured
  model, captures pass/fail, steps, tokens, cost (from a per-model price
  table), wall time, trace ids → `evals/results/<timestamp>-<model>.json`.
  `--tag` to label the prompt/tool variant.
* `evals/report.py` — prints a table and pass@1 / pass@k; `--compare a b`
  shows deltas between two result files.
* `python -m dockhand.trace <run_id>` — pretty-prints a trace: per step the
  exact system prompt (first time), messages delta, tool calls, response,
  tokens, latency. `--step N` to dump one full request as JSON.
* Baseline run recorded in Field notes: model, pass rate, mean steps, mean
  cost.

**Definition of done**

```bash
uv run python evals/run.py --trials 3 --tag baseline
uv run python evals/report.py evals/results/latest.json          # pass@1, pass@3, steps, tokens, $, seconds per task
# change one sentence in the system prompt, re-run with --tag v2, then:
uv run python evals/report.py --compare baseline v2
uv run python -m dockhand.trace <run_id> --step 4
```

**What you learn**: why evals are the core loop of AI engineering;
variance (run 3 trials and watch the same task pass 2/3); hidden tests
vs visible tests; cost per solved task; reading a trace to find *why* a
run failed (wrong tool? bad truncation? prompt ambiguity?).

---

## Step 5 — Persistence, Celery task, event bus, SSE

Goal: the loop runs in the worker, everything is recorded, and `curl` can
watch it live.

**Build**

* `dockhand/db/` — models per ARCHITECTURE §3, `init_db()`. Traces from
  Step 3 get a `run_id` ↔ `session_id` link.
* `dockhand/events/` — `Event` types, `publish()` (SQLite + `XADD`),
  `tail(session_id, after_id)` (`XREAD BLOCK` generator).
* `dockhand/worker.py` — `run_session(session_id)`: lock, status updates,
  sandbox create/attach, transcript load, `run_agent`, transcript save per
  turn (crash mid-run doesn't lose the conversation), outcome → status.
  Cancel flag in Redis.
* `dockhand/web/api.py` — `POST /api/sessions`, `GET`, `POST …/stop`.
* ✍️ `dockhand/web/stream.py` — **you write the SSE generator.** Per
  ARCHITECTURE §4: `Last-Event-ID`, replay-then-tail, keepalive, close on
  terminal status.

**Definition of done**

```bash
curl -X POST localhost:8000/api/sessions -d '{"prompt":"…","repo_url":"…"}' -H 'content-type: application/json'
curl -N localhost:8000/api/sessions/<id>/events        # live; Ctrl-C; re-run with -H 'Last-Event-ID: 12' → resumes
curl -X POST localhost:8000/api/sessions/<id>/stop     # status → cancelled within one step
```

**What you learn**: background job orchestration, locks and idempotency,
Redis Streams vs pub/sub, SSE mechanics, an event log both the UI and
replay can consume.

---

## Step 6 — Web UI (with trace view)

Goal: the product is usable by a human, and you can see what the model saw.

**Build**

* `templates/index.html` — new-task form + recent sessions.
* `templates/session.html` + `static/session.js` — `EventSource` client;
  timeline renderer for every event type; tool-call cards (collapsed,
  expandable, exit-code tint, truncated badge); status pill; token/cost
  counter; Stop button; auto-scroll with "jump to bottom".
* **Trace toggle** — each assistant turn has a "show prompt" control that
  reveals the exact request for that step (from the trace log): system
  prompt, message count, tools offered, tokens, latency. A mini
  LangSmith/Langfuse, built in.
* `static/app.css` — CSS variables, light/dark via `prefers-color-scheme`,
  single column under 768 px.
* Reload safety: page renders past events server-side, SSE continues from
  the last id.

**Definition of done**: run a real task from the browser on desktop and in a
phone-sized window; reload mid-run and nothing is lost; Stop works; open the
trace for a step and see the exact prompt.

**What you learn**: rendering agent traces (a core UX problem for every agent
product), SSE in the browser, progressive enhancement.

---

## Step 7 — Multi-turn, `ask_user`, diff & patch

Goal: the session is a conversation, not a one-shot; you can see and take
the result.

**Build**

* `POST /api/sessions/{id}/messages` — appends user message; re-enqueues
  `run_session`; worker resumes with the full transcript; sandbox reused if
  alive, recreated (+ warning event) if reaped.
* `ask_user` tool → `waiting_for_user`; composer highlighted; answer resumes.
* `GET /api/sessions/{id}/diff` + `/sessions/{id}/diff.patch`; diff drawer in
  the UI with +/- colouring; `diff.updated` after every mutating tool call.

**Definition of done**: ask for something under-specified → agent asks a
question → you answer → it finishes → review the diff → download the patch →
`git apply` locally, cleanly.

**What you learn**: conversation state across runs, human-in-the-loop as a
state machine, producing reviewable output from an agent.

---

## Step 8 — Hardening & polish (MVP complete)

Goal: it behaves like software, not a demo. In the 10-day track only the
first three bullets + `docker compose up` + tests are done on Day 7; the
rest is polish for later.

**Build**

* `reap_sandboxes` beat task; `make clean-sandboxes`.
* `MAX_SESSION_TOKENS`; friendly `session.error` for every limit.
* LLM error handling: retries, then fail the run with a clear message; tool
  exceptions never crash the loop.
* Structured logging (JSON lines) with `session_id` on every line.
* Usage panel: tokens, steps, wall time, cost; session list shows status + cost.
* `DELETE /api/sessions/{id}`.
* `docker compose up` runs everything; README quickstart verified from a
  clean clone; 30-second demo GIF.
* Tests green (`unit` always; `integration` when Docker present); `ruff` clean.
* Eval run recorded as the **MVP baseline**.

**Definition of done**: a stranger can clone, set three env vars,
`docker compose up`, and run a task. You can explain every line of the event
timeline and every number in the usage panel.

**What you learn**: the operational side of agents — cleanup, budgets,
failure handling, cost visibility — most of what turns a loop into a product.

---

## Step 9 — AI-engineering labs (primary learning track)

Each lab: **hypothesis → change → eval run → numbers → Field notes entry.**
If the numbers don't move (or get worse), that is a result too — write it
down.

**In the 10-day track:** 9.1, 9.3, 9.5. **Later:** 9.4, 9.2, 9.6, 9.8, 9.7.
(9.1 and 9.3 only need the CLI, so they can be pulled forward to right after
Step 4 if you're impatient.)

### 9.0 Framework comparison (1 h, *Later*)

Rewrite the Step 3 CLI run in **LangGraph** (or the OpenAI Agents SDK) in a
scratch file, using the same `FakeSandbox` tools and `FakeLLM` script. Map
each of your pieces onto theirs: `ToolRegistry.schemas()` → `bind_tools`,
`run_agent` → the graph, `TraceWriter` → LangSmith callbacks. Write five
lines in Field notes: what the framework buys, what it hides, what you would
lose control of in a coding agent. Interview answer: "built it, then compared
it" beats "know LangChain".

### 9.1 Context engineering & prompt caching

* ✍️ **Compaction** (you write it): when the transcript exceeds a token
  budget, summarise the oldest tool results into a single "progress so far"
  message; keep system, original task, and the last N turns verbatim. Emit a
  `context.compacted` event.
* **Scratchpad**: the agent may keep `/workspace/.dockhand/NOTES.md`; its
  contents are injected at the top of each step. External memory beats
  re-reading.
* **Cache-friendly prompts**: put everything static (system prompt, tool
  schemas) first and stable; never inject timestamps or random ordering.
  DeepSeek / Kimi / Qwen report cached prompt tokens in `usage` — record
  them and compute the hit rate and the cost saved.
* Measure: pass rate on long tasks, mean tokens per run, cache hit %.

### 9.2 Retrieval for code — embeddings vs lexical

* `semantic_search(query)` tool: chunk repo files (by function/class where
  possible, else fixed windows), embed with a local model
  (`sentence-transformers` with a BGE/Qwen embedding model, or a provider's
  embedding endpoint), store in `sqlite-vec` or a plain numpy index built at
  sandbox creation.
* Eval: same tasks, three configs — `search` (rg) only, `semantic_search`
  only, both. Compare pass rate, steps to first correct file, tokens.
* Write up when each wins. This is a live debate in the field; having your
  own numbers is rare and valuable.

### 9.3 Model routing, structured outputs, reasoning models

* **Routing**: a cheap model for session titles, summaries and compaction; the
  strong model for the loop; a fallback provider on repeated 5xx/429.
* **Structured outputs**: `response_format` with a JSON schema for the plan
  (9.5) and for `finish` summaries (`{summary, files_changed, how_verified}`).
* **Reasoning models**: use a thinking model (`deepseek-reasoner`,
  Kimi thinking, Qwen thinking mode) for a single planning turn only; keep the
  tool loop on the non-thinking model. Handle `reasoning_content` round-trips.
* Measure: cost per session before/after; pass rate with/without the
  reasoning planning turn.

### 9.4 Guardrails & permission modes

* Risk classifier for `bash` commands: fast rules (`rm -rf`, `git push
  --force`, `curl | sh`, writes outside `/workspace`) + an LLM classifier for
  the grey zone.
* New state `waiting_for_approval`; the UI shows the command with
  Approve / Deny; a per-session allowlist ("always allow `pytest`").
* Permission modes: `ask` (default), `auto` (evals), `read-only`.
* Measure: false-positive rate on the eval set (how often it asks for
  something harmless).

### 9.5 Planning & verification (LLM-as-judge)

* **Plan turn**: first call produces a checklist (structured output); the
  loop emits `plan.progress` as items complete; UI shows the plan.
* **Verifier**: before honouring `finish`, a separate LLM call reviews the
  task, the diff and the test output and returns `{approve, issues[]}`. If
  rejected, issues are fed back as a user message (max 2 rounds).
  ✍️ You write the verifier prompt.
* Measure: pass rate and cost with plan only, verifier only, both. Judge
  the judge: on 20 runs, compare verifier verdicts to the hidden tests.

### 9.6 MCP

* **Client**: `MCP_SERVERS` config; at session start, connect, list tools,
  merge them into the registry with a namespace (`fetch__get`, …). Try a
  docs/fetch server so the agent can read library docs.
* **Server** (optional): expose `bash`/`read_file`/`write_file` on a live
  sandbox as an MCP server, then drive Dockhand from Claude Desktop or
  Cursor.
* Measure: does doc access change pass rate on library-heavy tasks?

### 9.7 Fine-tuning (short, optional — *Later*)

Kept deliberately small. Enough to answer "prompt, RAG or fine-tune?" with
your own numbers, not a deep dive.

* `evals/export.py`: passing trajectories → JSONL chat format with tool
  calls, keys scrubbed, train/val split **by task** (not by row).
* One narrow fine-tune: the command-risk classifier from 9.4 (input: bash
  command → `safe | needs_approval | block`). Label ~300 examples with the
  strong model, hand-check 50, LoRA-train `Qwen2.5-0.5B-Instruct` with
  `mlx-lm` on the Mac (minutes), serve with `mlx_lm.server`
  (OpenAI-compatible → plugs into Dockhand unchanged).
* Measure accuracy / false positives / latency vs the prompted strong model.
* Skip distillation of the whole agent and DPO/RL; just know the words
  (SFT, DPO, GRPO, rejection sampling, distillation) and when teams use them.

~3 h. **What you learn**: what LoRA adapters are, chat templates, leakage,
serving a tuned model, and the canonical "narrow + high-volume +
latency-sensitive → fine-tune" answer.

### 9.8 Sub-agents & parallel tools

* Execute independent tool calls from one turn concurrently (reads/searches
  yes; writes/bash no — define the rule).
* `delegate(task, context)` tool: a child `run_agent` with a fresh
  transcript and a step budget, returning a summary. Try "write the tests"
  and "investigate this failure" delegations.
* Measure: wall time and pass rate; watch for the classic failure (child
  lacks context the parent had).

---

## Step 10 — Scale-out labs (system design)

Same format: **hypothesis → change → load → numbers → what broke.** Load is
free: `FakeLLM` + `FakeSandbox` let you fire 200 concurrent sessions with
zero tokens. Use `hey`/`locust` for HTTP load.

**In the 10-day track:** 10.2 and 10.3 (they reuse Traefik and Celery you
already have, ~2 h each; use `docker stats` and Celery's `inspect` for
numbers). **Later:** 10.1 first (nothing else is meaningful without metrics),
then 10.5, 10.4, 10.6–10.8.

### 10.1 Metrics
Prometheus + Grafana in compose. Queue depth, runs in flight, run duration
p50/p95, LLM latency, tokens/min, active sandboxes, SSE connections.

### 10.2 Load balancer & stateless web
`docker compose up --scale web=3`; Traefik round-robins. Open 50 SSE
streams, kill one web replica, watch clients reconnect via `Last-Event-ID`
with no lost events. Then break it on purpose: cache something in-process
and see the bug. Health checks.

### 10.3 Worker pool & crash recovery
3 workers, `acks_late=True`, `worker_prefetch_multiplier=1`, task time
limits, separate `runs` and `maintenance` queues. Kill a worker mid-run →
task re-delivered → lock lease expires → resumes from transcript. Measure
duplicate work.

### 10.4 Rate limiting & backpressure
Token bucket on `POST /sessions` (Redis). Global semaphore so all workers
together respect the provider's RPM. Bounded queue → 429 with a
`queued_position`. Load test until it degrades gracefully instead of falling over.

### 10.5 Caching
(a) LLM response cache keyed by hash(messages+tools) — hit rate in evals
(should be very high on re-runs). (b) Git clone cache: bare mirror volume,
`--reference`. (c) Cache-aside for `GET /api/sessions` with invalidation on
events. Measure hit rates and latency deltas.

### 10.6 Object storage
MinIO in compose; patches, full logs and traces stored as objects; presigned
download links; DB keeps only keys.

### 10.7 Postgres
SQLite → Postgres with Alembic migrations; pgbouncer; WAL/connection maths.
Load test the session list at 100k events.

### 10.8 Sharding lab (+ capacity doc)
Two honest options: **Redis Cluster** (3 masters, hash tags
`{session_id}`, kill a master, watch failover) or an **app-level shard
router** on a branch (`shard_{hash(id) % 4}.db`; session list becomes
scatter-gather; add a 5th shard and feel rebalancing). Either way, write
`docs/CAPACITY.md`: at what QPS / data size would Dockhand need this, and
what you'd do first (indexes, read replica, partitioning, archiving).

---

## Stretch

Well-bounded add-ons once the above is done: token streaming
(`agent.delta`), live terminal via xterm.js, GitHub PR creation, re-apply
last patch on sandbox recreation, `devcontainer.json` detection, auth and
multi-user, alternative sandbox backends (remote Docker, gVisor, hosted
sandbox API).

---

## Showing it

When demoing to the startup, the story that lands is not "I built a UI". It is:

1. **"Here are the numbers."** Open the eval report. Baseline vs. after
   each lab. Pass@3, cost per solved task, what moved and what didn't.
2. **"Here is the loop."** `agent/loop.py`, ~80 lines. Observe/act,
   stop conditions, truncation, compaction.
3. **"Here is what the model saw."** Open a trace for a failed run and walk
   through *why* it failed.
4. **"Here is the boundary."** `sandbox/manager.py`; `docker ps` during a run;
   the approval gate catching `rm -rf`.
5. **"Here is what it costs."** Usage panel; cache hit rate; routing savings.
6. Run a live task on a small repo, get a diff, download the patch.
