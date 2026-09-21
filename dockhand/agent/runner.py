"""Run one agent turn for a stored session: lock, sandbox, transcript, loop, record.

Everything the Celery task does lives here so it can be exercised with a
FakeLLM / FakeSandbox / fake Redis in tests. `run_session` is idempotent under
redelivery: a second delivery while the first holds the lock returns "locked".
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from dockhand.agent.loop import Limits, run_agent
from dockhand.agent.prompts import build_system_prompt, workspace_tree
from dockhand.agent.tools import default_registry
from dockhand.config import get_settings
from dockhand.db.engine import db_session
from dockhand.db.models import Message, Session
from dockhand.events import (
    EV_DIFF,
    EV_ERROR,
    EV_SANDBOX_READY,
    EV_STATUS,
    EV_TOOL_RESULT,
    EV_USAGE,
    EventBus,
    get_bus,
)
from dockhand.llm.client import LLMClient, make_llm
from dockhand.llm.trace import TraceWriter, new_run_id
from dockhand.llm.types import system_message, user_message
from dockhand.sandbox import Sandbox, SandboxNotFound, SandboxProtocol

log = logging.getLogger(__name__)

SandboxFactory = Callable[[str, str | None, str | None], SandboxProtocol]
MUTATING_TOOLS = {"write_file", "edit_file", "bash"}


def _default_sandbox_factory(
    session_id: str, repo_url: str | None, container_id: str | None
) -> SandboxProtocol:
    if container_id:
        try:
            return Sandbox.attach(container_id)
        except SandboxNotFound:
            log.info("session %s: container %s gone, recreating", session_id, container_id[:12])
    return Sandbox.create(session_id, repo_url=repo_url)


def run_session(
    session_id: str,
    *,
    llm: LLMClient | None = None,
    bus: EventBus | None = None,
    sandbox_factory: SandboxFactory = _default_sandbox_factory,
    limits: Limits | None = None,
) -> str:
    bus = bus or get_bus()
    settings = get_settings()
    owner = f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"
    if not bus.acquire_lock(session_id, owner):
        log.warning("session %s already running elsewhere; skipping", session_id)
        return "locked"

    try:
        with db_session() as db:
            sess = db.get(Session, session_id)
            if sess is None:
                return "missing"
            if sess.status == "running":
                return "already_running"
            cancelled_before_start = bus.is_cancelled(session_id)
            if cancelled_before_start:
                sess.status = "cancelled"
            else:
                sess.status = "running"
        if cancelled_before_start:
            bus.clear_cancel(session_id)
            bus.publish(session_id, EV_STATUS, {"status": "cancelled"})
            return "cancelled"
        with db_session() as db:
            sess = db.get(Session, session_id)
            sess.model = llm.model if llm else settings.llm_model
            prompt, repo_url, container_id = sess.prompt, sess.repo_url, sess.container_id
            prompt_version = sess.prompt_version
            transcript: list[dict[str, Any]] = [m.payload for m in sess.messages]
        bus.publish(session_id, EV_STATUS, {"status": "running"})

        sandbox = sandbox_factory(session_id, repo_url, container_id)
        reused = bool(container_id) and getattr(sandbox, "container_id", None) == container_id
        with db_session() as db:
            db.get(Session, session_id).container_id = getattr(sandbox, "container_id", None)
        bus.publish(
            session_id,
            EV_SANDBOX_READY,
            {
                "container_id": getattr(sandbox, "container_id", None),
                "repo_url": repo_url,
                "reused": reused,
            },
        )

        if not transcript:
            tree = workspace_tree(sandbox)
            transcript = [
                system_message(
                    build_system_prompt(tree=tree, repo_url=repo_url, version=prompt_version)
                ),
                user_message(prompt),
            ]
        saved = _persist_messages(session_id, transcript, already_saved=_count_messages(session_id))

        run_id = new_run_id()
        if llm is None:
            llm = make_llm(trace=TraceWriter(run_id))
        with db_session() as db:
            db.get(Session, session_id).last_run_id = run_id

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}

        def emit(kind: str, payload: dict[str, Any]) -> None:
            nonlocal saved
            if kind == EV_USAGE:
                payload = {**payload, "run_id": run_id}
                for k in usage:
                    usage[k] += payload[k]
            bus.publish(session_id, kind, payload)
            saved = _persist_messages(session_id, transcript, already_saved=saved)
            if kind == EV_TOOL_RESULT and payload.get("name") in MUTATING_TOOLS:
                try:
                    bus.publish(session_id, EV_DIFF, sandbox.diff_stat())
                except Exception:  # noqa: BLE001 — stats are cosmetic
                    log.debug("diff_stat failed", exc_info=True)

        outcome = run_agent(
            llm=llm,
            sandbox=sandbox,
            transcript=transcript,
            tools=default_registry(),
            emit=emit,
            should_cancel=lambda: bus.is_cancelled(session_id),
            limits=limits or Limits(),
        )
        _persist_messages(session_id, transcript, already_saved=saved)
        patch, stat = _capture_patch(sandbox)

        with db_session() as db:
            sess = db.get(Session, session_id)
            sess.status = outcome.status
            sess.patch = patch
            sess.diff_files, sess.diff_insertions, sess.diff_deletions = (
                stat["files"],
                stat["insertions"],
                stat["deletions"],
            )
            sess.steps += outcome.steps
            sess.prompt_tokens += usage["prompt_tokens"]
            sess.completion_tokens += usage["completion_tokens"]
            sess.cached_tokens += usage["cached_tokens"]
            sess.summary = outcome.summary or outcome.question or sess.summary
            sess.error = outcome.error
            sess.finished_at = datetime.now(UTC).replace(tzinfo=None)
        bus.clear_cancel(session_id)
        bus.publish(session_id, EV_STATUS, {"status": outcome.status, "error": outcome.error})
        return outcome.status

    except Exception as e:  # noqa: BLE001 — record, don't let Celery retry forever
        log.exception("session %s crashed", session_id)
        msg = f"{type(e).__name__}: {e}"
        with db_session() as db:
            sess = db.get(Session, session_id)
            if sess is not None:
                sess.status = "failed"
                sess.error = msg
                sess.finished_at = datetime.now(UTC).replace(tzinfo=None)
        bus.publish(session_id, EV_ERROR, {"message": msg, "recoverable": False})
        bus.publish(session_id, EV_STATUS, {"status": "failed", "error": msg})
        return "failed"
    finally:
        bus.release_lock(session_id, owner)


def _capture_patch(sandbox: SandboxProtocol) -> tuple[str | None, dict[str, int]]:
    """The run's diff and its stats, so they outlive the container."""
    try:
        return sandbox.diff() or None, sandbox.diff_stat()
    except Exception:  # noqa: BLE001 — never fail a finished run over a diff
        log.warning("could not capture patch", exc_info=True)
        return None, {"files": 0, "insertions": 0, "deletions": 0}


def _count_messages(session_id: str) -> int:
    with db_session() as db:
        return db.query(Message).filter(Message.session_id == session_id).count()


def _persist_messages(
    session_id: str, transcript: list[dict[str, Any]], *, already_saved: int
) -> int:
    if len(transcript) <= already_saved:
        return already_saved
    with db_session() as db:
        for seq in range(already_saved, len(transcript)):
            m = transcript[seq]
            db.add(Message(session_id=session_id, seq=seq, role=m["role"], payload=m))
    return len(transcript)
