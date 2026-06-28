from __future__ import annotations

import http.client
import json
import time
from typing import Any


SseFrame = dict[str, Any]


def request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    conn = http.client.HTTPConnection("localhost", 8000, timeout=10)
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    if response.status >= 400:
        raise RuntimeError(f"{method} {path} failed {response.status}: {data.decode()}")
    return json.loads(data or b"{}")


def upload_file(name: str, content: bytes, mime_type: str = "text/plain") -> dict[str, Any]:
    boundary = "agent-smoke-boundary"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    conn = http.client.HTTPConnection("localhost", 8000, timeout=10)
    conn.request(
        "POST",
        "/api/files",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    response = conn.getresponse()
    data = response.read()
    conn.close()
    if response.status >= 400:
        raise RuntimeError(f"POST /api/files failed {response.status}: {data.decode()}")
    return json.loads(data or b"{}")


def read_sse_until(
    conversation_id: str,
    stop_type: str = "RUN_FINISHED",
    bridge_result: bool = False,
    last_event_id: str | None = None,
) -> list[dict[str, Any]]:
    return [frame["data"] for frame in read_sse_frames_until(conversation_id, stop_type, bridge_result, last_event_id)]


def read_sse_frames_until(
    conversation_id: str,
    stop_type: str = "RUN_FINISHED",
    bridge_result: bool = False,
    last_event_id: str | None = None,
) -> list[SseFrame]:
    conn = http.client.HTTPConnection("localhost", 8000, timeout=10)
    headers = {"Last-Event-ID": last_event_id} if last_event_id else {}
    conn.request("GET", f"/api/conversations/{conversation_id}/events", headers=headers)
    response = conn.getresponse()
    if response.status != 200:
        raise RuntimeError(f"SSE failed {response.status}")

    frames: list[SseFrame] = []
    current: list[str] = []
    tool_call_id: str | None = None
    posted = False
    start = time.time()
    while time.time() - start < 15:
        line = response.readline().decode("utf-8")
        if line == "":
            break
        if line == "\n":
            id_lines = [part[4:].strip() for part in current if part.startswith("id:")]
            data_lines = [part[6:].strip() for part in current if part.startswith("data:")]
            if data_lines:
                event = json.loads("".join(data_lines))
                frames.append({"id": id_lines[-1] if id_lines else None, "data": event})
                if event["type"] == "TOOL_CALL_START":
                    tool_call_id = event["toolCallId"]
                if bridge_result and event["type"] == "TOOL_CALL_END" and tool_call_id and not posted:
                    request(
                        "POST",
                        f"/api/client-actions/{tool_call_id}/result",
                        {"status": "completed", "result": {"text": "selected text from smoke"}},
                    )
                    posted = True
                if event["type"] == stop_type:
                    break
            current = []
        else:
            current.append(line.rstrip("\n"))
    conn.close()
    return frames


def run_case(*, bridge: bool) -> list[str]:
    conversation = request("POST", "/api/conversations")
    assert isinstance(conversation, dict)
    context: dict[str, Any] = {}
    if bridge:
        context["bridge"] = {"enabled": True, "action_name": "get_selected_text", "timeout_ms": 5000}
    run = request(
        "POST",
        "/api/runs",
        {
            "conversation_id": conversation["conversation_id"],
            "client_id": conversation["client_id"],
            "message": {"type": "text", "content": "run bridge demo" if bridge else "run demo task"},
            "selected_agent_id": "demo_business_agent",
            "attachments": [],
            "context": context,
        },
    )
    assert isinstance(run, dict)
    events = read_sse_until(str(conversation["conversation_id"]), bridge_result=bridge)
    types = [str(event["type"]) for event in events]
    required = {"RUN_STARTED", "CUSTOM", "TEXT_MESSAGE_CONTENT", "RUN_FINISHED"}
    if bridge:
        required.update({"TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"})
    missing = required - set(types)
    if missing:
        raise RuntimeError(f"missing events for bridge={bridge}: {sorted(missing)}; saw {types}")
    return types


def run_replay_case() -> list[str]:
    conversation = request("POST", "/api/conversations")
    assert isinstance(conversation, dict)
    run = request(
        "POST",
        "/api/runs",
        {
            "conversation_id": conversation["conversation_id"],
            "client_id": conversation["client_id"],
            "message": {"type": "text", "content": "run replay demo"},
            "selected_agent_id": "demo_business_agent",
            "attachments": [],
            "context": {},
        },
    )
    assert isinstance(run, dict)
    frames = read_sse_frames_until(str(conversation["conversation_id"]))
    if len(frames) < 2 or not frames[0]["id"]:
        raise RuntimeError(f"not enough frames to verify replay: {frames}")

    replayed = read_sse_frames_until(str(conversation["conversation_id"]), last_event_id=str(frames[0]["id"]))
    replayed_types = [str(frame["data"]["type"]) for frame in replayed]
    if "RUN_STARTED" in replayed_types:
        raise RuntimeError(f"replay returned already acknowledged event; saw {replayed_types}")
    if "RUN_FINISHED" not in replayed_types:
        raise RuntimeError(f"replay did not reach run finish; saw {replayed_types}")
    if replayed and replayed[0]["id"] == frames[0]["id"]:
        raise RuntimeError(f"replay did not advance past Last-Event-ID: {replayed}")
    return replayed_types


def run_attachment_case() -> list[str]:
    uploaded = upload_file("smoke.txt", b"attachment smoke")
    conversation = request("POST", "/api/conversations")
    assert isinstance(conversation, dict)
    run = request(
        "POST",
        "/api/runs",
        {
            "conversation_id": conversation["conversation_id"],
            "client_id": conversation["client_id"],
            "message": {"type": "text", "content": "run attachment demo"},
            "selected_agent_id": "demo_business_agent",
            "attachments": [uploaded],
            "context": {},
        },
    )
    assert isinstance(run, dict)
    events = read_sse_until(str(conversation["conversation_id"]))
    ui_events = [
        event
        for event in events
        if event.get("type") == "CUSTOM" and event.get("name") == "ui.component.render"
    ]
    if not ui_events:
        raise RuntimeError(f"missing ui render event for attachment case; saw {events}")
    ui_value = ui_events[-1]["value"]
    attachments = ui_value.get("props", {}).get("attachments", [])
    if not attachments:
        raise RuntimeError(f"missing attachments in ui render; saw {ui_value}")
    echoed = attachments[0]
    for key in ("file_id", "name", "size_bytes"):
        if echoed.get(key) != uploaded.get(key):
            raise RuntimeError(f"attachment {key} mismatch: uploaded={uploaded}, echoed={echoed}")
    return [str(event["type"]) for event in events]


def run_cancel_case() -> list[str]:
    conversation = request("POST", "/api/conversations")
    assert isinstance(conversation, dict)
    run = request(
        "POST",
        "/api/runs",
        {
            "conversation_id": conversation["conversation_id"],
            "client_id": conversation["client_id"],
            "message": {"type": "text", "content": "run cancel demo"},
            "selected_agent_id": "demo_business_agent",
            "attachments": [],
            "context": {"demo_delay_ms": 500},
        },
    )
    assert isinstance(run, dict)
    request("POST", f"/api/runs/{run['run_id']}/cancel", {})
    events = read_sse_until(str(conversation["conversation_id"]), stop_type="RUN_ERROR")
    types = [str(event["type"]) for event in events]
    errors = [event for event in events if event["type"] == "RUN_ERROR"]
    if not errors or errors[-1].get("code") != "RUN_CANCEL_REQUESTED":
        raise RuntimeError(f"missing cancel event; saw {events}")
    if "RUN_FINISHED" in types:
        raise RuntimeError(f"cancelled run unexpectedly finished; saw {types}")
    return types


def main() -> None:
    capabilities = request("GET", "/api/capabilities")
    if not capabilities:
        raise RuntimeError("no capabilities returned")
    print("capabilities ok")
    print("normal", run_case(bridge=False))
    print("replay", run_replay_case())
    print("attachment", run_attachment_case())
    print("bridge", run_case(bridge=True))
    print("cancel", run_cancel_case())


if __name__ == "__main__":
    main()
