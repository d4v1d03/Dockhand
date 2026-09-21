"""The agent loop.

Keep it pure: no Celery, no HTTP, no SQLite in this file. Everything it
needs comes in through the arguments; everything it produces goes out through
`emit`, the returned `AgentOutcome`, and the `transcript` list it appends to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from dockhand.agent.tools import ToolRegistry
from dockhand.config import get_settings
from dockhand.events.types import (
    EV_ASK_USER,
    EV_ERROR,
    EV_MESSAGE,
    EV_TOOL_CALL,
    EV_TOOL_RESULT,
    EV_USAGE,
)
from dockhand.llm.client import LLMClient
from dockhand.llm.types import Message, ToolCall, tool_result_message
from dockhand.sandbox import SandboxProtocol

EmitFn = Callable[[str, dict[str, Any]], None]

Status = Literal["completed", "waiting_for_user", "failed", "cancelled"]


@dataclass
class Limits:
    max_steps: int = field(default_factory=lambda: get_settings().max_steps)


@dataclass
class AgentOutcome:
    status: Status
    steps: int
    summary: str | None = None  # the `finish` summary, or the final assistant text
    question: str | None = None  # the `ask_user` question
    error: str | None = None


def run_agent(
    *,
    llm: LLMClient,
    sandbox: SandboxProtocol,
    transcript: list[Message],
    tools: ToolRegistry,
    emit: EmitFn,
    should_cancel: Callable[[], bool] = lambda: False,
    limits: Limits | None = None,
) -> AgentOutcome:
    """Drive the model ↔ tools loop until it finishes, asks, fails or is cancelled.

    `transcript` must already hold the system prompt and the user's task (and,
    on a follow-up, the whole earlier conversation). It is appended to IN
    PLACE — one assistant message per turn, then one tool message per tool
    call — so the caller can persist it after every step.
    """
    limits = limits or Limits()
    steps = 0

    for step in range(1, limits.max_steps + 1):
        if should_cancel():
            return AgentOutcome(status="cancelled", steps=steps)

        try:
            turn = llm.chat(transcript, tools.schemas())
        except Exception as e:  # noqa: BLE001
            emit(EV_ERROR, {"message": f"LLM call failed: {e}", "recoverable": False})
            return AgentOutcome(status="failed", steps=steps, error=f"LLM call failed: {e}")
        steps = step
        emit(
            EV_USAGE,
            {
                "step": step,
                "prompt_tokens": turn.usage.prompt_tokens,
                "completion_tokens": turn.usage.completion_tokens,
                "cached_tokens": turn.usage.cached_tokens,
                "model": turn.model,
                "latency_ms": turn.latency_ms,
            },
        )

        transcript.append(turn.to_message())
        if turn.content:
            emit(EV_MESSAGE, {"content": turn.content})
        if not turn.tool_calls:
            return AgentOutcome(status="completed", steps=steps, summary=turn.content)

        for i, call in enumerate(turn.tool_calls):
            if should_cancel():
                _answer_remaining(transcript, turn.tool_calls[i:], "Cancelled by the user.")
                return AgentOutcome(status="cancelled", steps=steps)

            emit(EV_TOOL_CALL, {"call_id": call.id, "name": call.name, "arguments": call.arguments})
            result = tools.run(call, sandbox)
            emit(
                EV_TOOL_RESULT,
                {
                    "call_id": call.id,
                    "name": call.name,
                    "output": result.output,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                    "truncated": result.truncated,
                    "is_error": result.is_error,
                },
            )
            transcript.append(tool_result_message(call.id, result.output))

            if call.name == "finish":
                _answer_remaining(transcript, turn.tool_calls[i + 1 :], "Skipped: run finished.")
                return AgentOutcome(
                    status="completed", steps=steps, summary=call.arguments.get("summary")
                )
            if call.name == "ask_user":
                question = call.arguments.get("question", "")
                _answer_remaining(
                    transcript, turn.tool_calls[i + 1 :], "Skipped: waiting for the user."
                )
                emit(EV_ASK_USER, {"question": question})
                return AgentOutcome(status="waiting_for_user", steps=steps, question=question)

    msg = f"max steps ({limits.max_steps}) reached without finishing"
    emit(EV_ERROR, {"message": msg, "recoverable": False})
    return AgentOutcome(status="failed", steps=steps, error=msg)


def _answer_remaining(transcript: list[Message], calls: list[ToolCall], note: str) -> None:
    """When we stop mid-turn (cancel / finish / ask_user with more calls queued),
    every remaining tool call still needs a tool message, or the transcript is
    invalid for the next run. Answer them with a short note."""
    for call in calls:
        transcript.append(tool_result_message(call.id, note))
