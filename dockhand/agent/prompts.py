"""System prompt construction.

The prompt text lives in a versioned Markdown file (`prompts/system_v0.md`)
rather than an f-string in code so that (a) it can be diffed and evaluated
like any other artifact — prompt versions are compared on the eval suite —
and (b) it reads like what it is: instructions to the model.

`system_v0.md` is the baseline; new versions are new files, compared on the
eval suite before they become the default.
"""

from __future__ import annotations

from pathlib import Path

from dockhand.sandbox import SandboxProtocol

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT_VERSION = "v0"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def workspace_tree(sandbox: SandboxProtocol, depth: int = 2, max_lines: int = 150) -> str:
    """A shallow listing of /workspace for the prompt, so the model's first
    move is informed rather than a blind `ls`."""
    r = sandbox.exec(
        f"find . -maxdepth {depth} "
        r"\( -name .git -o -name node_modules -o -name .venv -o -name __pycache__ \) -prune "
        f"-o -print | sort | head -{max_lines}",
        timeout_s=30,
    )
    listing = r.output.strip() if r.ok else "(could not list workspace)"
    return listing or "(empty)"


def build_system_prompt(
    *,
    tree: str,
    repo_url: str | None = None,
    network: bool = True,
    version: str = SYSTEM_PROMPT_VERSION,
) -> str:
    template = load_prompt(f"system_{version}")
    return template.format(
        repo_line=f" (cloned from {repo_url})"
        if repo_url
        else " (empty; start a new project here)",
        network="yes" if network else "no",
        tree=tree,
    )
