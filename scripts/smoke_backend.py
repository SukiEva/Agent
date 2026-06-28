from __future__ import annotations

import http.client
import json
import time
from typing import Any


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


def read_sse_until(conversation_id: str, stop_type: str = "RUN_FINISHED", bridge_result: bool = False) -> list[dict[str, Any]]:
    conn = http.client.HTTPConnection("localhost", 8000, timeout=10)
    conn.request("GET", f"/api/conversations/{conversation_id}/events")
    response = conn.getresponse()
    if response.status != 200:
        raise RuntimeError(f"SSE failed {response.status}")

    events: list[dict[str, Any]] = []
    current: list[str] = []
    tool_call_id: str | None = None
    posted = False
    start = time.time()
    while time.time() - start < 15:
        line = response.readline().decode("utf-8")
        if line == "":
            break
        if line == "\n":
            data_lines = [part[6:].strip() for part in current if part.startswith("data:")]
            if data_lines:
                event = json.loads("".join(data_lines))
                events.append(event)
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
    return events


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
    print("bridge", run_case(bridge=True))
    print("cancel", run_cancel_case())


if __name__ == "__main__":
    main()
