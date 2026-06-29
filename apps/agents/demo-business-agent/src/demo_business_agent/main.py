from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_core.auth import build_internal_auth_headers
from agent_core.a2a import build_agent_card
from agent_core.config import load_service_config
from agent_core.llm import build_pydantic_agent, should_execute_model
from agent_core.logging import configure_service_logging
from agent_core.schemas.errors import AgentError
from agent_core.schemas.business import BusinessProgressEvent, BusinessResultEnvelope, DeliveryDirective
from agent_core.schemas.ui import UiDescriptor, UiFallback
from agent_core.serialization import json_line, to_dict
from agent_core.server import hypercorn_bind
from agent_core.stores import create_runtime_stores

_bridge_context: ContextVar[tuple[FastAPI, dict[str, Any]] | None] = ContextVar("bridge_context", default=None)


class DemoBusinessResult(BaseModel):
    summary: str
    items: list[str] = Field(default_factory=list)
    ui_title: str = "Demo Result"


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _settings() -> dict[str, Any]:
    return load_service_config(_conf_dir())


def create_app() -> FastAPI:
    app = FastAPI(title="Demo Business Agent")
    app.state.settings = _settings()
    configure_service_logging(app.state.settings)
    app.state.pydantic_agent = build_pydantic_agent(
        app.state.settings,
        system_prompt="Run the demo business task and return structured business results.",
    )
    app.state.pydantic_agent.tool_plain(
        call_frontend_bridge,
        name="call_frontend_bridge",
        description="Call a frontend bridge function in the user's active browser session.",
    )
    app.state.stores = create_runtime_stores(app.state.settings)
    app.state.cancelled_tasks = set()

    @app.on_event("startup")
    async def startup() -> None:
        _start_command_listener(app)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await _stop_command_listener(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/.well-known/agent-card.json")
    async def agent_card() -> dict[str, object]:
        return build_agent_card(app.state.settings)

    @app.post("/a2a/tasks")
    async def create_task(request: Request) -> StreamingResponse:
        payload = await request.json()

        async def stream():
            run_id = payload["run_id"]
            task_id = payload["task_id"]
            agent_id = app.state.settings["agent"]["id"]
            delay_ms = int(payload.get("context", {}).get("demo_delay_ms", 100))
            progress_messages = [
                "Demo agent accepted the task.",
                "Demo agent is preparing a component descriptor.",
                "Demo agent completed the fake business result.",
            ]
            for message in progress_messages:
                if _is_cancelled(app, task_id):
                    yield json_line(_cancelled_event(agent_id, run_id, task_id))
                    return
                await asyncio.sleep(delay_ms / 1000)
                if _is_cancelled(app, task_id):
                    yield json_line(_cancelled_event(agent_id, run_id, task_id))
                    return
                yield json_line(
                    to_dict(
                        BusinessProgressEvent(
                            agent_id=agent_id,
                            run_id=run_id,
                            task_id=task_id,
                            message=message,
                        )
                    )
                )
            if _is_cancelled(app, task_id):
                yield json_line(_cancelled_event(agent_id, run_id, task_id))
                return
            bridge_result = await _maybe_call_frontend_bridge(app, payload)
            if _is_cancelled(app, task_id):
                yield json_line(_cancelled_event(agent_id, run_id, task_id))
                return
            attachments = _attachment_summaries(payload)
            business_result = await _generate_business_result(app, payload, bridge_result, attachments)
            envelope = _business_result_envelope(
                agent_id=agent_id,
                run_id=run_id,
                task_id=task_id,
                result=business_result,
                bridge_result=bridge_result,
                attachments=attachments,
            )
            yield json_line({"type": "business.result", "envelope": to_dict(envelope)})

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/a2a/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, object]:
        app.state.cancelled_tasks.add(task_id)
        return {"status": "cancel_requested", "task_id": task_id}

    return app


def _business_result_envelope(
    *,
    agent_id: str,
    run_id: str,
    task_id: str,
    result: DemoBusinessResult,
    bridge_result: dict[str, object] | None,
    attachments: list[dict[str, object]],
) -> BusinessResultEnvelope:
    return BusinessResultEnvelope(
        status="completed",
        agent_id=agent_id,
        run_id=run_id,
        task_id=task_id,
        result_type="demo_result.v1",
        result={
            "summary": result.summary,
            "items": result.items,
            "bridge_result": bridge_result,
            "attachments": attachments,
        },
        ui=UiDescriptor(
            component="demo.result_card",
            component_version="v1",
            props={
                "title": result.ui_title,
                "summary": result.summary,
                "items": result.items,
                "attachments": attachments,
            },
            fallback=UiFallback(
                component="common.markdown",
                props={"content": result.summary},
            ),
        ),
        delivery=DeliveryDirective(mode="passthrough", final=True, needs_master_summary=False),
    )


async def call_frontend_bridge(
    action_name: str,
    args: dict[str, object],
    timeout_ms: int = 30000,
) -> dict[str, object]:
    context = _bridge_context.get()
    if context is None:
        return {"status": "unavailable", "error": "frontend bridge context is not available"}
    app, payload = context
    return await _call_frontend_bridge_request(app, payload, action_name, args, timeout_ms)


async def _generate_business_result(
    app: FastAPI,
    payload: dict[str, Any],
    bridge_result: dict[str, object] | None,
    attachments: list[dict[str, object]],
) -> DemoBusinessResult:
    if not should_execute_model(app.state.settings):
        return _fallback_business_result(payload)
    token = _bridge_context.set((app, payload))
    try:
        result = await app.state.pydantic_agent.run(
            _business_result_prompt(payload, bridge_result, attachments),
            output_type=DemoBusinessResult,
        )
        output = _agent_output(result)
        if isinstance(output, DemoBusinessResult):
            return output
        if isinstance(output, dict):
            return DemoBusinessResult(**output)
        return DemoBusinessResult.model_validate(output)
    except Exception:
        return _fallback_business_result(payload)
    finally:
        _bridge_context.reset(token)


def _business_result_prompt(
    payload: dict[str, Any],
    bridge_result: dict[str, object] | None,
    attachments: list[dict[str, object]],
) -> str:
    request = {
        "user_message": _user_message_text(payload),
        "attachments": attachments,
        "bridge_result": bridge_result,
    }
    return (
        "Generate a concise demo business result for the user. "
        "Return only the structured DemoBusinessResult fields requested by the output schema. "
        "Use call_frontend_bridge only if you need live browser context beyond the provided bridge_result.\n\n"
        f"{json.dumps(request, ensure_ascii=False, separators=(',', ':'))}"
    )


def _fallback_business_result(payload: dict[str, Any]) -> DemoBusinessResult:
    return DemoBusinessResult(
        summary=f"Processed: {_user_message_text(payload)}",
        items=["A2A routing worked", "SSE replay path is ready", "UI descriptor delivered"],
        ui_title="Demo Result",
    )


def _agent_output(result: Any) -> Any:
    for attr in ("output", "data"):
        if hasattr(result, attr):
            return getattr(result, attr)
    return result

def _user_message_text(payload: dict[str, Any]) -> str:
    message = payload.get("user_message")
    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            return str(content)
    return str(message or "")


def _is_cancelled(app: FastAPI, task_id: str) -> bool:
    return task_id in app.state.cancelled_tasks


def _attachment_summaries(payload: dict[str, Any]) -> list[dict[str, object]]:
    attachments = payload.get("attachments", [])
    if not isinstance(attachments, list):
        return []
    summaries: list[dict[str, object]] = []
    for attachment in attachments:
        if not isinstance(attachment, dict) or "file_id" not in attachment:
            continue
        summaries.append(
            {
                "file_id": str(attachment["file_id"]),
                "name": str(attachment.get("name") or ""),
                "mime_type": attachment.get("mime_type"),
                "size_bytes": attachment.get("size_bytes"),
            }
        )
    return summaries


def _start_command_listener(app: FastAPI) -> None:
    if app.state.settings.get("runtime", {}).get("store") != "redis":
        app.state.command_listener = None
        return
    app.state.command_listener = asyncio.create_task(_listen_for_commands(app))


async def _stop_command_listener(app: FastAPI) -> None:
    listener = getattr(app.state, "command_listener", None)
    if listener is None:
        return
    listener.cancel()
    try:
        await listener
    except asyncio.CancelledError:
        return


async def _listen_for_commands(app: FastAPI) -> None:
    agent_id = app.state.settings["agent"]["id"]
    async for command in app.state.stores.commands.stream(agent_id):
        if command.get("type") == "cancel_task":
            app.state.cancelled_tasks.add(str(command["task_id"]))


def _cancelled_event(agent_id: str, run_id: str, task_id: str) -> dict[str, object]:
    return {
        "type": "business.error",
        "agent_id": agent_id,
        "run_id": run_id,
        "task_id": task_id,
        "error": to_dict(
            AgentError(
                code="TASK_CANCELLED",
                message="Task was cancelled.",
                recoverable=True,
                retryable=True,
                cancelled=True,
            )
        ),
    }


async def _maybe_call_frontend_bridge(app: FastAPI, payload: dict[str, Any]) -> dict[str, object] | None:
    bridge = payload.get("context", {}).get("bridge")
    if not isinstance(bridge, dict) or not bridge.get("enabled"):
        return None

    action_name = str(bridge.get("action_name", "get_selected_text"))
    args = bridge.get("args") if isinstance(bridge.get("args"), dict) else {}
    return await _call_frontend_bridge_request(app, payload, action_name, args, int(bridge.get("timeout_ms", 30000)))


async def _call_frontend_bridge_request(
    app: FastAPI,
    payload: dict[str, Any],
    action_name: str,
    args: dict[str, object],
    timeout_ms: int,
) -> dict[str, object]:
    import httpx

    agent_server_base_url = app.state.settings.get("agent_server", {}).get("base_url", "http://localhost:8000")
    agent_id = app.state.settings["agent"]["id"]
    headers = build_internal_auth_headers(
        app.state.settings,
        service_id=agent_id,
        agent_id=agent_id,
    )
    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        response = await client.post(
            f"{agent_server_base_url}/internal/client-actions",
            headers=headers,
            json={
                "conversation_id": payload["conversation_id"],
                "run_id": payload["run_id"],
                "agent_id": agent_id,
                "action_name": action_name,
                "args": args,
                "timeout_ms": timeout_ms,
            },
        )
        response.raise_for_status()
        return response.json()


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = hypercorn_bind(app.state.settings)
    asyncio.run(hypercorn.asyncio.serve(app, config))
