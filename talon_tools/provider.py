"""
Provider protocol — the interface every LLM backend must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import Context, StreamEvent


class Provider(ABC):
    """Abstract LLM provider.

    Implementations wrap a specific SDK or API (Copilot, OpenAI, Anthropic, etc.)
    and translate to/from the talon-ai types.
    """

    @abstractmethod
    async def start(self) -> None:
        """Initialize the provider (connect, authenticate, etc.)."""

    @abstractmethod
    async def stop(self) -> None:
        """Shut down the provider and release resources."""

    @abstractmethod
    async def stream(self, context: Context) -> AsyncIterator[StreamEvent]:
        """Stream a response for the given context.

        The provider MUST handle tool execution internally:
        1. Yield TextDelta events for text chunks
        2. When the model requests tool calls, execute them using context.tools
        3. Continue streaming until the model stops or an error occurs

        Yields StreamEvent instances (TextDelta, ToolCallEnd, StreamDone, etc.)
        """

    async def complete(self, context: Context) -> str:
        """Send a message and return the full response text.

        Default implementation collects stream() output. Providers can override
        for a more efficient non-streaming path.
        """
        from .types import TextDelta, StreamDone
        chunks: list[str] = []
        async for event in self.stream(context):
            if isinstance(event, TextDelta):
                chunks.append(event.delta)
            elif isinstance(event, StreamDone):
                if event.content and not chunks:
                    return event.content
                break
        return "".join(chunks)
