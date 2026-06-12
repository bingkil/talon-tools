"""
Core types for the LLM abstraction layer.

Canonical home is talon-oss (talon.types). This module re-exports everything
from there for backward compatibility — existing ``from talon_tools import Tool``
imports continue to work unchanged.
"""

from talon.types import *  # noqa: F401, F403
from talon.types import (
    Tool, ToolResult, StopReason, ToolCall,
    UserMessage, AssistantMessage, ToolResultMessage, Message,
    Context, TokenUsage,
    TextDelta, ToolCallStart, ToolCallDelta, ToolCallEnd,
    StreamDone, StreamError, StreamEvent,
)
