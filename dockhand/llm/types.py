"""Data types for talking to a chat model with tools.

The *transcript* — the list of messages sent to the model — is kept as plain
dicts in the OpenAI chat format, because that is (a) exactly what the API
wants, (b) JSON-serialisable for the database and the trace log, and (c)
readable when you dump it. Helpers below build the three message shapes.

    {"role": "system",    "content": "..."}
    {"role": "user",      "content": "..."}
    {"role": "assistant", "content": "...", "tool_calls": [{...}]}
    {"role": "tool",      "tool_call_id": "call_abc", "content": "..."}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

Message = dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """One function call the model asked for."""

    id: str  # provider-generated; must be echoed back in the tool result
    name: str
    arguments: dict[str, Any]  # parsed JSON; {} if the model produced invalid JSON
    raw_arguments: str = ""  # what the model actually wrote, for traces/errors
    # Provider-specific fields that must be echoed back with the call on the
    # next turn (e.g. Gemini's `extra_content.google.thought_signature`).
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0  # part of prompt_tokens served from the provider's cache

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
            self.cached_tokens + other.cached_tokens,
        )


@dataclass
class AssistantTurn:
    """The model's reply to one `chat()` call, normalised across providers."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    model: str = ""
    finish_reason: str | None = None
    # "Thinking" models (DeepSeek reasoner, Kimi thinking) return their
    # reasoning separately, and some providers require it to be sent back
    # with the assistant message on the next turn. Kept verbatim.
    reasoning: str | None = None

    def to_message(self) -> Message:
        """The assistant message to append to the transcript."""
        msg: Message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.raw_arguments or json.dumps(tc.arguments),
                    },
                    **tc.extra,
                }
                for tc in self.tool_calls
            ]
        if self.reasoning:
            msg["reasoning_content"] = self.reasoning
        return msg


def system_message(content: str) -> Message:
    return {"role": "system", "content": content}


def user_message(content: str) -> Message:
    return {"role": "user", "content": content}


def tool_result_message(call_id: str, content: str) -> Message:
    """Every tool call the model made needs exactly one of these, in order —
    OpenAI-compatible APIs reject a transcript with a dangling tool call."""
    return {"role": "tool", "tool_call_id": call_id, "content": content}
