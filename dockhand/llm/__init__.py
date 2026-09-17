"""LLM access: one OpenAI-compatible client for every provider, a fake for
tests, and the transcript message types."""

from dockhand.llm.client import FakeLLM, LLMClient, OpenAICompatibleClient
from dockhand.llm.types import (
    AssistantTurn,
    Message,
    ToolCall,
    Usage,
    system_message,
    tool_result_message,
    user_message,
)

__all__ = [
    "AssistantTurn",
    "FakeLLM",
    "LLMClient",
    "Message",
    "OpenAICompatibleClient",
    "ToolCall",
    "Usage",
    "system_message",
    "tool_result_message",
    "user_message",
]
