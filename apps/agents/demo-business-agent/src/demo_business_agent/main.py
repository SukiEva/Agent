from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from agent_core.a2a import build_agent_card
from agent_core.config import load_service_config
from agent_core.logging import configure_service_logging
from agent_core.schemas.errors import AgentError
from agent_core.schemas.business import BusinessProgressEvent, BusinessResultEnvelope, DeliveryDirective
from agent_core.schemas.ui import UiDescriptor, UiFallback
from agent_core.serialization import json_line, to_dict
from agent_core.stores import create_runtime_stores


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _settings() -> dict[str, Any]:
    return load_service_config(_conf_dir())


def create_app() -> FastAPI:
    app = FastAPI(title="Demo Business Agent")
    app.state.settings = _settings()
    configure_service_logging(app.state.settings)
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
            envelope = BusinessResultEnvelope(
                status="completed",
                agent_id=agent_id,
                run_id=run_id,
                task_id=task_id,
                result_type="demo_result.v1",
                result={
                    "summary": f"Processed: {payload['user_message']['content']}",
                    "items": ["A2A routing worked", "SSE replay path is ready", "UI descriptor delivered"],
                    "bridge_result": bridge_result,
                },
                ui=UiDescriptor(
                    component="demo.result_card",
                    component_version="v1",
                    props={
                        "title": "Demo Result",
                        "summary": f"Processed: {payload['user_message']['content']}",
                        "items": ["A2A routing worked", "SSE replay path is ready", "UI descriptor delivered"],
                    },
                    fallback=UiFallback(
                        component="common.markdown",
                        props={"content": "Demo result completed."},
                    ),
                ),
                delivery=DeliveryDirective(mode="passthrough", final=True, needs_master_summary=False),
            )
            yield json_line({"type": "business.result", "envelope": to_dict(envelope)})

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/a2a/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, object]:
        app.state.cancelled_tasks.add(task_id)
        return {"status": "cancel_requested", "task_id": task_id}

    return app


def _is_cancelled(app: FastAPI, task_id: str) -> bool:
    return task_id in app.state.cancelled_tasks


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
    import httpx

    action_name = str(bridge.get("action_name", "get_selected_text"))
    args = bridge.get("args") if isinstance(bridge.get("args"), dict) else {}
    agent_server_base_url = app.state.settings.get("agent_server", {}).get("base_url", "http://localhost:8000")
    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        response = await client.post(
            f"{agent_server_base_url}/internal/client-actions",
            json={
                "conversation_id": payload["conversation_id"],
                "run_id": payload["run_id"],
                "agent_id": app.state.settings["agent"]["id"],
                "action_name": action_name,
                "args": args,
                "timeout_ms": int(bridge.get("timeout_ms", 30000)),
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
    config.bind = ["0.0.0.0:8011"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
