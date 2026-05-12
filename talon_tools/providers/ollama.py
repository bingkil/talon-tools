"""
Ollama provider — uses the OpenAI-compatible endpoint exposed by Ollama.

Ollama serves at http://localhost:11434/v1 by default.
Override with OLLAMA_BASE_URL environment variable.
"""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

from openai import AsyncOpenAI

from talon_tools import Provider
from talon_tools import (
    Context, StreamEvent, TextDelta, StreamDone, StreamError,
    Tool, ToolCall, StopReason, TokenUsage,
)

log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434/v1"


def _to_openai_tool(tool: Tool) -> dict:
    """Convert a talon Tool to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class OllamaProvider(Provider):
    """Provider implementation for Ollama via OpenAI-compatible API."""

    def __init__(self, model: str = "gemma4:e4b", base_url: str | None = None):
        self._model = model
        self._base_url = base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        self._client: AsyncOpenAI | None = None

    async def start(self) -> None:
        self._client = AsyncOpenAI(
            api_key="ollama",  # required by SDK, ignored by Ollama
            base_url=self._base_url,
        )
        log.info("Ollama client started (base_url=%s, model=%s)", self._base_url, self._model)

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def stream(self, context: Context) -> AsyncIterator[StreamEvent]:
        """Stream a response from Ollama, handling tool calls in a loop."""
        if self._client is None:
            await self.start()

        model = context.model or self._model
        messages = self._build_messages(context)
        tools_spec = [_to_openai_tool(t) for t in context.tools] if context.tools else None
        tool_map = {t.name: t for t in context.tools} if context.tools else {}

        for _ in range(20):  # safety cap
            try:
                kwargs: dict = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                }
                if tools_spec:
                    kwargs["tools"] = tools_spec

                log.debug("Ollama request: %d messages, model=%s", len(messages), model)

                stream = await self._client.chat.completions.create(**kwargs)

                full_text: list[str] = []
                tool_calls_acc: dict[int, dict] = {}

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    if delta.content:
                        full_text.append(delta.content)
                        yield TextDelta(delta=delta.content)

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc.id or "",
                                    "name": tc.function.name if tc.function and tc.function.name else "",
                                    "args": "",
                                }
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["args"] += tc.function.arguments

                if not tool_calls_acc:
                    usage = None
                    if hasattr(stream, "usage") and stream.usage:
                        usage = TokenUsage(
                            input_tokens=stream.usage.prompt_tokens or 0,
                            output_tokens=stream.usage.completion_tokens or 0,
                            total_tokens=stream.usage.total_tokens or 0,
                        )
                    yield StreamDone(
                        stop_reason=StopReason.STOP,
                        content="".join(full_text),
                        usage=usage,
                    )
                    return

                # Execute tool calls
                text_content = "".join(full_text)
                assistant_msg: dict = {"role": "assistant", "content": text_content or ""}
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"] or f"call_{i}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["args"]},
                    }
                    for i, tc in enumerate(sorted(tool_calls_acc.values(), key=lambda x: x["id"]))
                ]
                messages.append(assistant_msg)

                sent_tool_calls = assistant_msg["tool_calls"]
                for tc_entry in sent_tool_calls:
                    name = tc_entry["function"]["name"]
                    raw_args = tc_entry["function"]["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    tool = tool_map.get(name)
                    if tool:
                        result = await tool.handler(args)
                        content = str(result.content) if result.content else "OK"
                    else:
                        content = f"Unknown tool: {name}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_entry["id"],
                        "content": content,
                    })

                full_text = []

            except Exception as exc:
                log.error("Ollama stream error — last 3 messages: %s",
                          json.dumps(messages[-3:], default=str, ensure_ascii=False)[:2000])
                log.exception("Ollama stream error")
                yield StreamError(error=str(exc))
                return

        yield StreamDone(stop_reason=StopReason.STOP, content="".join(full_text) if full_text else "")

    def _build_messages(self, context: Context) -> list[dict]:
        """Convert Context messages to OpenAI format."""
        messages: list[dict] = []
        if context.system_prompt:
            messages.append({"role": "system", "content": context.system_prompt})
        for msg in context.messages:
            if msg.role == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "tool_result":
                messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
        return messages
