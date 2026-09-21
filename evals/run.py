"""Run the agent on the eval tasks and record what happened.

    uv run python evals/run.py --trials 1 --tag baseline
    uv run python evals/run.py --tasks csv_to_json,word_freq --prompt v1 --tag v1
    uv run python evals/run.py --models gemini-3.6-flash,gemini-3.8-flash   # round-robin

Results land in evals/results/<timestamp>-<tag>.json (and latest.json).
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dockhand.agent.loop import EV_TOOL_CALL, EV_USAGE, Limits, run_agent  # noqa: E402
from dockhand.agent.prompts import (  # noqa: E402
    SYSTEM_PROMPT_VERSION,
    build_system_prompt,
    workspace_tree,
)
from dockhand.agent.tools import default_registry  # noqa: E402
from dockhand.config import get_settings  # noqa: E402
from dockhand.llm.client import OpenAICompatibleClient  # noqa: E402
from dockhand.llm.trace import TraceWriter, new_run_id  # noqa: E402
from dockhand.llm.types import system_message, user_message  # noqa: E402
from dockhand.sandbox import Sandbox  # noqa: E402
from evals.prices import cost_usd  # noqa: E402
from evals.tasks import Task, load_tasks  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class RunResult:
    task: str
    trial: int
    model: str
    prompt_version: str
    status: str
    passed: bool
    steps: int
    tool_calls: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float | None
    seconds: float
    check_exit: int | None
    check_output: str
    run_id: str
    summary: str | None
    error: str | None
    infra_error: bool


def run_one(
    task: Task, trial: int, model: str, prompt_version: str, max_steps: int | None
) -> RunResult:
    run_id = new_run_id()
    trace = TraceWriter(run_id)
    settings = get_settings()
    llm = OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=model,
        temperature=settings.llm_temperature,
        trace=trace,
    )
    tools = default_registry()
    usage = {"prompt": 0, "completion": 0, "cached": 0}
    counters = {"tool_calls": 0}

    def emit(kind: str, payload: dict) -> None:
        if kind == EV_USAGE:
            usage["prompt"] += payload["prompt_tokens"]
            usage["completion"] += payload["completion_tokens"]
            usage["cached"] += payload["cached_tokens"]
        elif kind == EV_TOOL_CALL:
            counters["tool_calls"] += 1

    t0 = time.monotonic()
    sandbox = Sandbox.create(f"eval-{secrets.token_hex(3)}", repo_url=task.repo_url)
    try:
        for path, content in task.setup.items():
            sandbox.write_file(path, content)
        transcript = [
            system_message(
                build_system_prompt(
                    tree=workspace_tree(sandbox), repo_url=task.repo_url, version=prompt_version
                )
            ),
            user_message(task.prompt.strip()),
        ]
        limits = Limits(max_steps=max_steps or task.max_steps or settings.max_steps)
        outcome = run_agent(
            llm=llm, sandbox=sandbox, transcript=transcript, tools=tools, emit=emit, limits=limits
        )

        check_exit: int | None = None
        check_output = ""
        if task.check and outcome.status == "completed":
            for path, content in task.hidden.items():
                sandbox.write_file(path, content)
            r = sandbox.exec(task.check, timeout_s=300)
            check_exit, check_output = r.exit_code, r.output[-2000:]
    finally:
        sandbox.destroy()

    seconds = time.monotonic() - t0
    return RunResult(
        task=task.name,
        trial=trial,
        model=model,
        prompt_version=prompt_version,
        status=outcome.status,
        passed=task.passed(outcome.status, check_exit),
        steps=outcome.steps,
        tool_calls=counters["tool_calls"],
        prompt_tokens=usage["prompt"],
        completion_tokens=usage["completion"],
        cached_tokens=usage["cached"],
        cost_usd=cost_usd(model, usage["prompt"], usage["completion"], usage["cached"]),
        seconds=round(seconds, 1),
        check_exit=check_exit,
        check_output=check_output,
        run_id=run_id,
        summary=outcome.summary or outcome.question,
        error=outcome.error,
        infra_error=bool(outcome.error and "LLM call failed" in outcome.error),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals/run.py")
    ap.add_argument("--tasks", help="comma-separated task names (default: all)")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--tag", default="run")
    ap.add_argument(
        "--prompt", default=SYSTEM_PROMPT_VERSION, help="system prompt version, e.g. v1"
    )
    ap.add_argument(
        "--models", help="comma-separated model ids, used round-robin (default: LLM_MODEL)"
    )
    ap.add_argument("--max-steps", type=int)
    args = ap.parse_args(argv)

    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    models = args.models.split(",") if args.models else [get_settings().llm_model]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"{stamp}-{args.tag}.json"

    results: list[RunResult] = []
    i = 0
    print(f"{len(tasks)} task(s) × {args.trials} trial(s) · prompt {args.prompt} · models {models}")
    for trial in range(1, args.trials + 1):
        for task in tasks:
            model = models[i % len(models)]
            i += 1
            print(f"[{i:>2}] {task.name} (trial {trial}, {model}) ... ", end="", flush=True)
            r = run_one(task, trial, model, args.prompt, args.max_steps)
            results.append(r)
            mark = "PASS" if r.passed else ("ERR " if r.infra_error else "FAIL")
            cost = f"${r.cost_usd:.4f}" if r.cost_usd is not None else "n/a"
            tok = r.prompt_tokens + r.completion_tokens
            line = f"{mark}  {r.status:<16} {r.steps:>2} steps  {tok:>6} tok  {cost}"
            print(f"{line}  {r.seconds:>4.0f}s")
            payload = {
                "tag": args.tag,
                "prompt_version": args.prompt,
                "models": models,
                "started": stamp,
                "results": [asdict(x) for x in results],
            }
            out.write_text(json.dumps(payload, indent=1))  # save after every run
            (RESULTS_DIR / "latest.json").write_text(json.dumps(payload, indent=1))

    n_pass = sum(r.passed for r in results)
    print(f"\n{n_pass}/{len(results)} passed → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
