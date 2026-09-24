# Roadmap

## Done

- Sandbox manager over the Docker Engine API: per-session containers, non-root,
  capabilities dropped, resource limits, in-container timeouts, tar-based file
  transfer, diff and diff stats.
- Agent loop with tool calling (`bash`, `read_file`, `write_file`, `edit_file`,
  `list_files`, `search`, `ask_user`, `finish`) and a provider-agnostic
  OpenAI-compatible client.
- Per-call trace log and a trace viewer (CLI and per-step view in the UI).
- Eval harness: task suite with hidden tests, pass@k, cost per solved task,
  comparison between tagged runs; versioned system prompts.
- Persistence (sessions, transcript, events), Celery worker with leases and
  crash-safe transcript writes, Redis Streams + SSE with gap-free resume.
- Web UI: live timeline, tool cards, usage counter, stop, follow-ups,
  `ask_user`, per-step prompt view, diff panel and `.patch` download.
- Demo model (`LLM_BASE_URL=fake`) for running the stack without a key.

- Maintenance: beat-scheduled sandbox reaper and a sweeper that re-queues
  sessions orphaned by a dead worker; per-session token budget; session
  deletion.
- Horizontal scaling verified: three `web` replicas behind Traefik with
  gap-free SSE resume across a replica failure; worker crash recovery with
  heartbeat leases, transcript repair and per-turn accounting.

- Evals on DeepSeek: prompt v1 cut tokens per task 32% at equal pass rate;
  cache-friendly prompt layout (0% → 88% of a new session's first request
  cached); context compaction implemented and measured as a net cost at
  typical context sizes, so off by default; confidence intervals on every
  pass rate.
- Thinking level as a setting; measured 20% cheaper off than on at the same
  pass rate.
- A reviewer before `finish` (LLM-as-judge) with JSON-mode structured output,
  and a harness that scores it against hidden tests and planted bugs; diffs
  taken against the session's start so committed work is kept.

## Next

- A stronger ask-when-unclear behaviour: the under-specified task passes ~80%,
  and the failures cost 10–20× a pass. The reviewer doesn't catch these.
- A cheaper reviewer (thinking off) and a harder task set where the agent's
  own tests are weak, to see whether the reviewer pays for itself.
- Model routing and provider failover through a gateway in front of
  `LLM_BASE_URL` (ADR-022).

## Later

- Approval gate for risky commands; permission modes.
- Semantic code search alongside ripgrep.
- MCP client support for external tools.
- Sub-agents and parallel tool execution.
- Token streaming; live terminal output.
- Re-apply the stored patch when a reaped sandbox is recreated.
- Branch push / pull-request creation.
- Multi-user auth; alternative sandbox backends (remote Docker, gVisor).
