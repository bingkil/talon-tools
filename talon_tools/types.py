"""
Core types for the LLM abstraction layer.

Provider-agnostic — any LLM backend implements the Provider protocol
using these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """A tool the model can invoke."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable[[dict[str, Any]], Awaitable[ToolResult]]

@dataclass
class ToolResult:
    """Result returned from a tool execution."""
    content: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class StopReason(Enum):
    STOP = "stop"           # Normal completion
    TOOL_USE = "tool_use"   # Model wants to call tools
    LENGTH = "length"       # Hit token limit
    ERROR = "error"         # Something went wrong

@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class UserMessage:
    role: str = field(default="user", init=False)
    content: str
    attachments: list[dict[str, Any]] | None = None

@dataclass
class AssistantMessage:
    role: str = field(default="assistant", init=False)
    content: str
    tool_calls: list[ToolCall] | None = None
    stop_reason: StopReason = StopReason.STOP

@dataclass
class ToolResultMessage:
    role: str = field(default="tool_result", init=False)
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False

Message = UserMessage | AssistantMessage | ToolResultMessage


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@dataclass
class Context:
    """Conversation context — serializable, transferable between providers."""
    system_prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    tools: list[Tool] = field(default_factory=list)
    model: str = ""
    timeout: float = 0  # Provider-level timeout in seconds; 0 = use default


# ---------------------------------------------------------------------------
# Token Usage
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    """Token counts from a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Stream events
# ---------------------------------------------------------------------------

@dataclass
class TextDelta:
    """A chunk of text from the model."""
    type: str = field(default="text_delta", init=False)
    delta: str = ""

@dataclass
class ToolCallStart:
    """Model started a tool call."""
    type: str = field(default="tool_call_start", init=False)
    tool_call_id: str = ""
    name: str = ""

@dataclass
class ToolCallDelta:
    """Partial arguments streaming for a tool call."""
    type: str = field(default="tool_call_delta", init=False)
    tool_call_id: str = ""
    delta: str = ""

@dataclass
class ToolCallEnd:
    """Tool call arguments complete."""
    type: str = field(default="tool_call_end", init=False)
    tool_call: ToolCall | None = None

@dataclass
class StreamDone:
    """Stream finished."""
    type: str = field(default="done", init=False)
    stop_reason: StopReason = StopReason.STOP
    content: str = ""  # full accumulated text
    usage: TokenUsage | None = None

@dataclass
class StreamError:
    """Stream error."""
    type: str = field(default="error", init=False)
    error: str = ""

StreamEvent = TextDelta | ToolCallStart | ToolCallDelta | ToolCallEnd | StreamDone | StreamError
