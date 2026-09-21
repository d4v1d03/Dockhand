"""Summarise eval results.

uv run python evals/report.py                         # latest.json
uv run python evals/report.py evals/results/x.json
uv run python evals/report.py --compare baseline v1   # tags or file paths
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load(ref: str) -> dict:
    p = Path(ref)
    if p.exists():
        return json.loads(p.read_text())
    matches = sorted(RESULTS_DIR.glob(f"*-{ref}.json"))
    if not matches:
        raise SystemExit(f"no results file for {ref!r}")
    return json.loads(matches[-1].read_text())


def summarise(payload: dict) -> dict[str, dict]:
    """Per task: pass@1 (mean over trials), pass@k (any trial), means of the rest."""
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in payload["results"]:
        by_task[r["task"]].append(r)
    out = {}
    for task, rs in by_task.items():
        real = [r for r in rs if not r["infra_error"]] or rs
        n = len(real)
        costs = [r["cost_usd"] for r in real if r["cost_usd"] is not None]
        out[task] = {
            "trials": len(rs),
            "infra_errors": sum(r["infra_error"] for r in rs),
            "pass@1": sum(r["passed"] for r in real) / n,
            "pass@k": float(any(r["passed"] for r in real)),
            "steps": sum(r["steps"] for r in real) / n,
            "tokens": sum(r["prompt_tokens"] + r["completion_tokens"] for r in real) / n,
            "cached%": 100
            * sum(r["cached_tokens"] for r in real)
            / max(1, sum(r["prompt_tokens"] for r in real)),
            "cost": sum(costs) / len(costs) if costs else None,
            "seconds": sum(r["seconds"] for r in real) / n,
        }
    return out


def totals(s: dict[str, dict]) -> dict:
    n = len(s) or 1
    costs = [v["cost"] for v in s.values() if v["cost"] is not None]
    return {
        "trials": sum(v["trials"] for v in s.values()),
        "infra_errors": sum(v["infra_errors"] for v in s.values()),
        "pass@1": sum(v["pass@1"] for v in s.values()) / n,
        "pass@k": sum(v["pass@k"] for v in s.values()) / n,
        "steps": sum(v["steps"] for v in s.values()) / n,
        "tokens": sum(v["tokens"] for v in s.values()) / n,
        "cached%": sum(v["cached%"] for v in s.values()) / n,
        "cost": sum(costs) / len(costs) if costs else None,
        "seconds": sum(v["seconds"] for v in s.values()) / n,
    }


def fmt_row(name: str, v: dict) -> str:
    cost = f"${v['cost']:.4f}" if v["cost"] is not None else "   n/a "
    return (
        f"{name:<22} {v['pass@1']:>6.0%} {v['pass@k']:>6.0%} {v['steps']:>6.1f} "
        f"{v['tokens']:>8.0f} {v['cached%']:>6.1f}% {cost:>8} {v['seconds']:>6.0f}s"
        + (f"  ({v['infra_errors']} infra err)" if v["infra_errors"] else "")
    )


HEADER = (
    f"{'task':<22} {'pass@1':>6} {'pass@k':>6} {'steps':>6} "
    f"{'tokens':>8} {'cached':>7} {'cost':>8} {'time':>7}"
)


def print_report(payload: dict) -> None:
    s = summarise(payload)
    print(
        f"tag={payload['tag']} prompt={payload['prompt_version']} "
        f"models={payload['models']} ({payload['started']})"
    )
    print(HEADER)
    for task, v in s.items():
        print(fmt_row(task, v))
    print("-" * len(HEADER))
    print(fmt_row("ALL", totals(s)))


def print_compare(a: dict, b: dict) -> None:
    sa, sb = summarise(a), summarise(b)
    ta, tb = totals(sa), totals(sb)
    print(f"{'':<22} {a['tag']:>16} {b['tag']:>16} {'delta':>10}")
    for task in sorted(set(sa) | set(sb)):
        va, vb = sa.get(task), sb.get(task)
        pa = f"{va['pass@1']:.0%}" if va else "-"
        pb = f"{vb['pass@1']:.0%}" if vb else "-"
        d = f"{(vb['pass@1'] - va['pass@1']):+.0%}" if va and vb else ""
        print(f"{task:<22} {pa:>16} {pb:>16} {d:>10}")
    print("-" * 68)
    for key, fmt in [
        ("pass@1", "{:.0%}"),
        ("steps", "{:.1f}"),
        ("tokens", "{:.0f}"),
        ("cost", "${:.4f}"),
        ("seconds", "{:.0f}s"),
    ]:
        xa, xb = ta[key], tb[key]
        fa = fmt.format(xa) if xa is not None else "n/a"
        fb = fmt.format(xb) if xb is not None else "n/a"
        d = ""
        if xa not in (None, 0) and xb is not None:
            d = f"{(xb - xa) / xa:+.0%}"
        print(f"{'ALL ' + key:<22} {fa:>16} {fb:>16} {d:>10}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals/report.py")
    ap.add_argument("ref", nargs="?", default=str(RESULTS_DIR / "latest.json"))
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    args = ap.parse_args(argv)
    if args.compare:
        print_compare(load(args.compare[0]), load(args.compare[1]))
    else:
        print_report(load(args.ref))
    return 0


if __name__ == "__main__":
    sys.exit(main())
