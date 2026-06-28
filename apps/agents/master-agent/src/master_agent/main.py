from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from agent_core.config import load_service_config
from agent_core.events import (
    agui_custom,
    agui_text_delta,
    agui_text_end,
    agui_text_start,
)
from agent_core.ids import new_message_id
from agent_core.logging import configure_service_logging
from agent_core.serialization import json_line, parse_json_line


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _settings() -> dict[str, Any]:
    return load_service_config(_conf_dir())


def create_app() -> FastAPI:
    app = FastAPI(title="Master Agent")
    app.state.settings = _settings()
    configure_service_logging(app.state.settings)
    app.state.cancelled_tasks = set()
    app.state.active_targets = {}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/.well-known/agent-card.json")
    async def agent_card() -> dict[str, object]:
        agent = app.state.settings["agent"]
        return {
            "name": agent["id"],
            "description": agent["display"]["description"],
            "url": "http://localhost:8010",
            "metadata": agent,
        }

    @app.post("/a2a/tasks")
    async def create_task(request: Request) -> StreamingResponse:
        payload = await request.json()

        async def stream():
            task_id = str(payload["task_id"])
            target_agent_id = payload.get("selected_agent_id") or await _choose_default_business_agent(app)
            if not target_agent_id:
                message_id = new_message_id()
                yield json_line(agui_text_start(message_id))
                yield json_line(agui_text_delta(message_id, "No available business agent was found."))
                yield json_line(agui_text_end(message_id))
                return
            app.state.active_targets[task_id] = target_agent_id

            import httpx

            gateway_base_url = app.state.settings["gateway"]["base_url"]
            try:
                async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
                    async with client.stream(
                        "POST",
                        f"{gateway_base_url}/a2a/{target_agent_id}/tasks",
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if task_id in app.state.cancelled_tasks:
                                return
                            if not line.strip():
                                continue
                            event = parse_json_line(line)
                            async for agui_event in _business_to_agui(event):
                                yield json_line(agui_event)
            finally:
                app.state.active_targets.pop(task_id, None)
                app.state.cancelled_tasks.discard(task_id)

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/a2a/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, object]:
        app.state.cancelled_tasks.add(task_id)
        target_agent_id = app.state.active_targets.get(task_id)
        if target_agent_id:
            await _cancel_business_task(app, target_agent_id, task_id)
        return {"status": "cancel_requested", "task_id": task_id, "target_agent_id": target_agent_id}

    return app


async def _choose_default_business_agent(app: FastAPI) -> str | None:
    import httpx

    gateway_base_url = app.state.settings["gateway"]["base_url"]
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(f"{gateway_base_url}/agents")
        response.raise_for_status()
    for agent in response.json():
        if agent.get("role") == "business" and agent.get("visibility") == "public" and agent.get("healthy", True):
            return str(agent["agent_id"])
    return None


async def _cancel_business_task(app: FastAPI, target_agent_id: str, task_id: str) -> None:
    import httpx

    gateway_base_url = app.state.settings["gateway"]["base_url"]
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            await client.post(f"{gateway_base_url}/a2a/{target_agent_id}/tasks/{task_id}/cancel")
    except Exception:
        return


async def _business_to_agui(event: dict[str, Any]):
    event_type = event.get("type")
    if event_type == "business.progress":
        yield agui_custom(
            "business.progress",
            {
                "agent_id": event["agent_id"],
                "run_id": event["run_id"],
                "task_id": event["task_id"],
                "message": event["message"],
            },
        )
        return

    if event_type == "business.result":
        envelope = event["envelope"]
        result = envelope.get("result", {})
        message_id = new_message_id()
        summary = str(result.get("summary") or "Business task completed.")
        yield agui_text_start(message_id)
        yield agui_text_delta(message_id, summary)
        yield agui_text_end(message_id)
        ui = envelope.get("ui")
        if ui:
            yield agui_custom("ui.component.render", ui)
        return

    if event_type == "business.error":
        yield agui_custom("business.error", event)


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:8010"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
