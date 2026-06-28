from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class SseEvent:
    id: str
    data: dict[str, object]
    event: str = "message"

    def encode(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {self.id}\nevent: {self.event}\ndata: {payload}\n\n"


async def encode_sse_events(events: AsyncIterator[SseEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield event.encode()


def agui_run_started(run_id: str) -> dict[str, object]:
    return {"type": "RUN_STARTED", "runId": run_id}


def agui_run_finished(run_id: str) -> dict[str, object]:
    return {"type": "RUN_FINISHED", "runId": run_id}


def agui_run_error(run_id: str, message: str, code: str = "RUN_ERROR") -> dict[str, object]:
    return {"type": "RUN_ERROR", "runId": run_id, "message": message, "code": code}


def agui_text_start(message_id: str, role: str = "assistant") -> dict[str, object]:
    return {"type": "TEXT_MESSAGE_START", "messageId": message_id, "role": role}


def agui_text_delta(message_id: str, delta: str) -> dict[str, object]:
    return {"type": "TEXT_MESSAGE_CONTENT", "messageId": message_id, "delta": delta}


def agui_text_end(message_id: str) -> dict[str, object]:
    return {"type": "TEXT_MESSAGE_END", "messageId": message_id}


def agui_tool_call_start(tool_call_id: str, name: str, parent_message_id: str | None = None) -> dict[str, object]:
    event: dict[str, object] = {
        "type": "TOOL_CALL_START",
        "toolCallId": tool_call_id,
        "toolCallName": name,
    }
    if parent_message_id:
        event["parentMessageId"] = parent_message_id
    return event


def agui_tool_call_args(tool_call_id: str, delta: str) -> dict[str, object]:
    return {"type": "TOOL_CALL_ARGS", "toolCallId": tool_call_id, "delta": delta}


def agui_tool_call_end(tool_call_id: str) -> dict[str, object]:
    return {"type": "TOOL_CALL_END", "toolCallId": tool_call_id}


def agui_tool_call_result_status(tool_call_id: str, status: str) -> dict[str, object]:
    return {"type": "TOOL_CALL_RESULT", "toolCallId": tool_call_id, "content": {"status": status}}


def agui_custom(name: str, value: dict[str, object]) -> dict[str, object]:
    return {"type": "CUSTOM", "name": name, "value": value}
