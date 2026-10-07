"""Server-Sent Events helpers for streaming chat responses.

Two SSE formats:
- Internal API (``/api/agents/{id}/chat?stream=true``): JSON events with
  ``type`` field (token, tool_call, tool_result, blocked, done).
- OpenAI-compatible (``/v1/chat/completions`` with ``stream=true``): OpenAI
  chunk format with ``delta.content``.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator

from app.llm.agent_runtime import StreamEvent


def _sse_data(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def stream_openai_sse(
    events: AsyncIterator[StreamEvent], model: str
) -> AsyncIterator[str]:
    """Format agent stream events as OpenAI-compatible SSE chunks."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def _chunk(delta: dict, finish_reason: str | None = None) -> str:
        return _sse_data(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {"index": 0, "delta": delta, "finish_reason": finish_reason}
                ],
            }
        )

    async for event in events:
        if event.type == "token":
            yield _chunk({"role": "assistant", "content": event.content})
        elif event.type == "blocked":
            yield _chunk({}, finish_reason="content_filter")
            yield "data: [DONE]\n\n"
            return
        elif event.type == "done":
            yield _chunk({}, finish_reason="stop")
            yield "data: [DONE]\n\n"
            return
        # tool_call and tool_result events are not surfaced in OpenAI SSE format.

    yield _chunk({}, finish_reason="stop")
    yield "data: [DONE]\n\n"
