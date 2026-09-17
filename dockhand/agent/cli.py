"""Run the agent from the terminal, no web stack needed.

    uv run python -m dockhand.agent.cli "Add a --version flag and a test for it" --repo https://github.com/you/repo
    uv run python -m dockhand.agent.cli "Create a CSV→JSON CLI with tests"        # empty workspace

Prints every event as it happens, the outcome, the diff, and where the trace
was written. The eval harness drives runs the same way.
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import sys
import time
from typing import Any

from dockhand.agent.loop import (
    EV_ASK_USER,
    EV_ERROR,
    EV_MESSAGE,
    EV_TOOL_CALL,
    EV_TOOL_RESULT,
    EV_USAGE,
    Limits,
    run_agent,
)
from dockhand.agent.prompts import build_system_prompt, workspace_tree
from dockhand.agent.tools import default_registry
from dockhand.llm.client import OpenAICompatibleClient
from dockhand.llm.trace import TraceWriter, new_run_id
from dockhand.llm.types import system_message, user_message
from dockhand.sandbox import Sandbox

# ANSI colours for the terminal; harmless if the terminal ignores them.
DIM, BOLD, CYAN, GREEN, RED, YELLOW, RESET = (
    "\033[2m",
    "\033[1m",
    "\033[36m",
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[0m",
)


def _summarise_call(name: str, args: dict[str, Any]) -> str:
    if name == "bash":
        return f"$ {args.get('command', '')}"
    if name in ("read_file", "write_file", "edit_file"):
        return str(args.get("path", ""))
    if name == "search":
        return f"/{args.get('pattern', '')}/ in {args.get('path', '.')}"
    if name in ("finish", "ask_user"):
        return ""
    return json.dumps(args)[:120]


def print_event(kind: str, payload: dict[str, Any]) -> None:
    if kind == EV_MESSAGE:
        print(f"\n{BOLD}assistant:{RESET} {payload['content']}")
    elif kind == EV_TOOL_CALL:
        summary = _summarise_call(payload["name"], payload["arguments"])
        print(f"\n{CYAN}▶ {payload['name']}{RESET} {summary}")
    elif kind == EV_TOOL_RESULT:
        colour = RED if payload.get("is_error") else DIM
        out = payload["output"]
        if len(out) > 1500:
            out = out[:1500] + f"\n{DIM}… ({len(payload['output'])} chars total){RESET}"
        print(f"{colour}{out}{RESET}")
        extra = []
        if payload.get("duration_ms"):
            extra.append(f"{payload['duration_ms']} ms")
        if payload.get("truncated"):
            extra.append("truncated")
        if extra:
            print(f"{DIM}  [{', '.join(extra)}]{RESET}")
    elif kind == EV_ASK_USER:
        print(f"\n{YELLOW}? {payload['question']}{RESET}")
    elif kind == EV_USAGE:
        p = payload
        print(
            f"{DIM}  step {p['step']}: {p['prompt_tokens']}+{p['completion_tokens']} tokens "
            f"({p['cached_tokens']} cached), {p['latency_ms']} ms{RESET}"
        )
    elif kind == EV_ERROR:
        print(f"\n{RED}error: {payload['message']}{RESET}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m dockhand.agent.cli")
    parser.add_argument("task", help="what the agent should do")
    parser.add_argument("--repo", help="public http(s) git URL to clone into the sandbox")
    parser.add_argument("--max-steps", type=int, help="override MAX_STEPS")
    parser.add_argument("--no-network", action="store_true", help="sandbox without internet")
    parser.add_argument(
        "--keep", action="store_true", help="leave the container running afterwards"
    )
    parser.add_argument("--no-diff", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", help="show library logs")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    run_id = new_run_id()
    trace = TraceWriter(run_id)
    llm = OpenAICompatibleClient.from_settings(trace=trace)
    tools = default_registry()
    limits = Limits(max_steps=args.max_steps) if args.max_steps else Limits()

    session_id = f"cli-{secrets.token_hex(3)}"
    print(f"{DIM}run {run_id} · session {session_id} · model {llm.model}{RESET}")
    t0 = time.monotonic()
    sandbox = Sandbox.create(session_id, repo_url=args.repo, network=not args.no_network)
    print(f"{DIM}sandbox {sandbox.container_id[:12]} ready in {time.monotonic() - t0:.1f}s{RESET}")

    try:
        tree = workspace_tree(sandbox)
        transcript = [
            system_message(
                build_system_prompt(tree=tree, repo_url=args.repo, network=not args.no_network)
            ),
            user_message(args.task),
        ]
        outcome = run_agent(
            llm=llm,
            sandbox=sandbox,
            transcript=transcript,
            tools=tools,
            emit=print_event,
            limits=limits,
        )
        colour = (
            GREEN
            if outcome.status == "completed"
            else YELLOW
            if outcome.status == "waiting_for_user"
            else RED
        )
        elapsed = time.monotonic() - t0
        print(
            f"\n{colour}{BOLD}{outcome.status}{RESET} after {outcome.steps} step(s), {elapsed:.0f}s"
        )
        if outcome.summary:
            print(outcome.summary)
        if outcome.question:
            print(f"question for you: {outcome.question}")
        if outcome.error:
            print(f"{RED}{outcome.error}{RESET}")
        if not args.no_diff:
            diff = sandbox.diff()
            print(f"\n{BOLD}--- diff ---{RESET}")
            print(diff.strip() or "(no changes)")
        print(f"\n{DIM}trace: {trace.path}{RESET}")
        return 0 if outcome.status in ("completed", "waiting_for_user") else 1
    finally:
        if args.keep:
            print(f"{DIM}kept: docker exec -it {sandbox.container_id[:12]} bash{RESET}")
        else:
            sandbox.destroy()


if __name__ == "__main__":
    sys.exit(main())
