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

## Next

- Sandbox reaper (Celery beat) and a sweeper for sessions stuck in `running`
  past their lease.
- Per-session token budget; `DELETE /api/sessions/{id}`.
- Context compaction and cache-friendly prompt layout, measured on the evals.
- Model routing (cheap model for titles and summaries), structured outputs,
  a reasoning model for a single planning turn.
- Plan-then-execute with a verifier pass before `finish`.

## Later

- Approval gate for risky commands; permission modes.
- Semantic code search alongside ripgrep.
- MCP client support for external tools.
- Sub-agents and parallel tool execution.
- Token streaming; live terminal output.
- Re-apply the stored patch when a reaped sandbox is recreated.
- Branch push / pull-request creation.
- Multi-user auth; alternative sandbox backends (remote Docker, gVisor).
