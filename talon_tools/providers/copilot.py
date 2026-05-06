"""
GitHub Copilot provider — wraps the copilot Python SDK behind the Provider interface.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from copilot import CopilotClient
from copilot.session import PermissionHandler
from copilot.generated.session_events import SessionEventType
from copilot.tools import Tool as CopilotTool, ToolInvocation, ToolResult as CopilotToolResult

from talon_tools import Provider
from talon_tools import (
    Context, StreamEvent, TextDelta, StreamDone, StreamError,
    Tool, ToolResult, StopReason, TokenUsage,
)

log = logging.getLogger(__name__)


def _to_copilot_tool(tool: Tool) -> CopilotTool:
    """Convert a talon-ai Tool to a Copilot SDK Tool."""
    async def handler(invocation: ToolInvocation) -> CopilotToolResult:
        result = await tool.handler(invocation.arguments)
        return CopilotToolResult(
            text_result_for_llm=result.content,
            result_type="error" if result.is_error else "success",
        )

    return CopilotTool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        handler=handler,
    )


class CopilotProvider(Provider):
    """Provider implementation for GitHub Copilot SDK."""

    def __init__(self, model: str = "claude-sonnet-4.6"):
        self._model = model
        self._client: CopilotClient | None = None
        self._session = None

    async def start(self) -> None:
        log.info("Starting Copilot client…")
        self._client = CopilotClient()
        await self._client.start()
        log.info("Copilot client started")

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.stop()
            except Exception:
                log.exception("Error stopping Copilot client")
            self._client = None
            self._session = None

    async def _ensure_session(self, context: Context) -> None:
        """Create or recreate the Copilot session with current context settings."""
        if self._session is not None:
            return

        if self._client is None:
            await self.start()

        model = context.model or self._model
        copilot_tools = [_to_copilot_tool(t) for t in context.tools] if context.tools else None

        self._session = await self._client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
            system_message={"mode": "replace", "content": context.system_prompt},
            tools=copilot_tools,
        )
        log.info("Copilot session created (model=%s)", model)

    async def _reset_session(self, context: Context) -> None:
        """Tear down and rebuild the session."""
        log.warning("Resetting Copilot session")
        await self.stop()
        await self._ensure_session(context)

    async def stream(self, context: Context) -> AsyncIterator[StreamEvent]:
        """Stream a response from Copilot.

        Handles the send_and_wait + event listener pattern from the SDK.
        Retries once on empty response (dead session recovery).
        """
        # Extract the last user message text and attachments
        last_msg = context.messages[-1] if context.messages else None
        if last_msg is None or last_msg.role != "user":
            yield StreamError(error="No user message in context")
            return

        text = last_msg.content
        attachments = getattr(last_msg, "attachments", None)

        for attempt in range(2):
            await self._ensure_session(context)

            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            got_deltas = False
            usage: TokenUsage | None = None

            def on_event(event):
                nonlocal got_deltas, usage
                if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                    delta = event.data.delta_content or ""
                    if delta:
                        got_deltas = True
                        chunk_queue.put_nowait(delta)
                elif event.type == SessionEventType.ASSISTANT_USAGE:
                    usage = TokenUsage(
                        input_tokens=int(event.data.input_tokens or 0),
                        output_tokens=int(event.data.output_tokens or 0),
                        cache_read_tokens=int(event.data.cache_read_tokens or 0),
                        cache_write_tokens=int(event.data.cache_write_tokens or 0),
                        total_tokens=int(event.data.total_tokens or 0),
                    )

            unsubscribe = self._session.on(on_event)
            response_task = None
            try:
                timeout = context.timeout or 300
                response_task = asyncio.create_task(
                    self._session.send_and_wait(text, attachments=attachments, timeout=timeout)
                )

                full_text = []
                while not response_task.done():
                    try:
                        chunk = await asyncio.wait_for(chunk_queue.get(), timeout=0.5)
                        full_text.append(chunk)
                        yield TextDelta(delta=chunk)
                    except asyncio.TimeoutError:
                        continue

                # Drain remaining
                while not chunk_queue.empty():
                    chunk = chunk_queue.get_nowait()
                    full_text.append(chunk)
                    yield TextDelta(delta=chunk)

                if got_deltas:
                    yield StreamDone(stop_reason=StopReason.STOP, content="".join(full_text), usage=usage)
                    return

                # No deltas — check full response
                response = response_task.result()
                if response and response.data and response.data.content:
                    content = response.data.content
                    yield TextDelta(delta=content)
                    yield StreamDone(stop_reason=StopReason.STOP, content=content, usage=usage)
                    return

                # Empty — dead session
                if attempt == 0:
                    log.warning("Empty response, resetting session (attempt %d)", attempt)
                    unsubscribe()
                    await self._reset_session(context)
                    continue

                yield StreamDone(stop_reason=StopReason.STOP, content="")
                return

            except GeneratorExit:
                if response_task and not response_task.done():
                    response_task.cancel()
                raise
            except Exception as exc:
                log.exception("Copilot stream error")
                if response_task and not response_task.done():
                    response_task.cancel()
                if attempt == 0:
                    unsubscribe()
                    await self._reset_session(context)
                    continue
                yield StreamError(error=str(exc))
                return
            finally:
                unsubscribe()
