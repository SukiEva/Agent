from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent_core.auth import AuthError, build_internal_authenticator, build_user_authenticator
from agent_core.config import load_service_config
from agent_core.events import (
    agui_run_error,
    agui_run_finished,
    agui_run_started,
    agui_tool_call_args,
    agui_tool_call_end,
    agui_tool_call_result_status,
    agui_tool_call_start,
    encode_sse_events,
)
from agent_core.files import build_file_store
from agent_core.ids import new_action_id, new_client_id, new_conversation_id, new_run_id, new_task_id
from agent_core.schemas.bridge import ClientActionCreate, ClientActionRequest, ClientActionResult
from agent_core.schemas.run import BusinessTaskRequest, RunRequest
from agent_core.serialization import parse_json_line, to_dict
from agent_core.stores import RuntimeStores, create_runtime_stores


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _settings() -> dict[str, Any]:
    return load_service_config(_conf_dir())


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Server")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = _settings()
    app.state.stores = create_runtime_stores(app.state.settings)
    app.state.user_auth = build_user_authenticator(app.state.settings)
    app.state.internal_auth = build_internal_authenticator(app.state.settings)
    app.state.file_store = build_file_store(app.state.settings, cwd=Path.cwd())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/conversations")
    async def create_conversation(request: Request) -> dict[str, str]:
        await _authenticate_user(app, request)
        conversation_id = new_conversation_id()
        client_id = new_client_id()
        await app.state.stores.conversations.create(conversation_id, client_id)
        return {"conversation_id": conversation_id, "client_id": client_id}

    @app.get("/api/conversations/{conversation_id}/events")
    async def conversation_events(
        conversation_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        await _authenticate_user(app, request)
        conversation = await app.state.stores.conversations.get(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="conversation not found")
        events = app.state.stores.events.stream(conversation_id, after_event_id=last_event_id)
        return StreamingResponse(encode_sse_events(events), media_type="text/event-stream")

    @app.get("/api/capabilities")
    async def capabilities(request: Request) -> list[dict[str, object]]:
        await _authenticate_user(app, request)
        import httpx

        gateway_base_url = app.state.settings["gateway"]["base_url"]
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(f"{gateway_base_url}/agents")
            response.raise_for_status()
        agents = response.json()
        return [
            _capability_from_agent(agent)
            for agent in agents
            if agent.get("role") == "business" and agent.get("visibility") == "public"
        ]

    @app.post("/api/files")
    async def upload_file(request: Request, file: UploadFile = File(...)) -> dict[str, object]:
        await _authenticate_user(app, request)
        content = await file.read()
        ref = await app.state.file_store.put_bytes(
            name=file.filename or "upload",
            content=content,
            mime_type=file.content_type,
        )
        return ref.model_dump(mode="json")

    @app.post("/api/runs")
    async def create_run(run_request: RunRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
        await _authenticate_user(app, request)
        conversation = await app.state.stores.conversations.get(run_request.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="conversation not found")
        run_id = new_run_id()
        task_id = new_task_id()
        await app.state.stores.runs.create(
            run_id,
            {
                "conversation_id": run_request.conversation_id,
                "task_id": task_id,
                "status": "queued",
                "selected_agent_id": run_request.selected_agent_id,
            },
        )
        await app.state.stores.events.append(run_request.conversation_id, agui_run_started(run_id))
        task_request = BusinessTaskRequest(
            conversation_id=run_request.conversation_id,
            run_id=run_id,
            task_id=task_id,
            client_id=run_request.client_id,
            user_message=run_request.message,
            selected_agent_id=run_request.selected_agent_id,
            attachments=run_request.attachments,
            context=run_request.context,
            client_context_token=f"client:{run_request.conversation_id}:{run_request.client_id}",
        )
        background_tasks.add_task(_run_master_task, app, task_request)
        return {"run_id": run_id, "root_task_id": task_id}

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, request: Request) -> dict[str, object]:
        await _authenticate_user(app, request)
        run = await app.state.stores.runs.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        await app.state.stores.runs.update(run_id, status="cancel_requested")
        await _cancel_master_task(app, str(run["task_id"]))
        await app.state.stores.events.append(
            str(run["conversation_id"]),
            agui_run_error(run_id, "Run cancellation requested.", code="RUN_CANCEL_REQUESTED"),
        )
        return {"status": "cancel_requested", "run_id": run_id}

    @app.post("/api/client-actions/{action_id}/result")
    async def complete_client_action(action_id: str, request: Request) -> dict[str, object]:
        await _authenticate_user(app, request)
        payload = await request.json()
        payload.pop("action_id", None)
        result = ClientActionResult(action_id=action_id, **payload)
        completed = await app.state.stores.client_actions.complete(result)
        return to_dict(completed)

    @app.post("/internal/client-actions")
    async def create_internal_client_action(action_request: ClientActionCreate, request: Request) -> dict[str, object]:
        await _authenticate_internal(app, request)
        conversation = await app.state.stores.conversations.get(action_request.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="conversation not found")
        action = ClientActionRequest(action_id=new_action_id(), **to_dict(action_request))
        await app.state.stores.client_actions.create(action)
        await app.state.stores.events.append(
            action_request.conversation_id,
            agui_tool_call_start(action.action_id, action_request.action_name),
        )
        await app.state.stores.events.append(
            action_request.conversation_id,
            agui_tool_call_args(action.action_id, json.dumps(action_request.args, ensure_ascii=False)),
        )
        await app.state.stores.events.append(action_request.conversation_id, agui_tool_call_end(action.action_id))
        try:
            result = await app.state.stores.client_actions.wait(action.action_id, action_request.timeout_ms)
        except TimeoutError:
            result = ClientActionResult(action_id=action.action_id, status="timeout")
            await app.state.stores.client_actions.complete(result)
        await app.state.stores.events.append(
            action_request.conversation_id,
            agui_tool_call_result_status(action.action_id, result.status),
        )
        return to_dict(result)

    return app


def _capability_from_agent(agent: dict[str, Any]) -> dict[str, object]:
    display = agent.get("display") or {}
    return {
        "agent_id": agent["agent_id"],
        "label": display.get("label", agent["agent_id"]),
        "description": display.get("description", ""),
        "available": bool(agent.get("healthy", True)),
        "capabilities": agent.get("capabilities", []),
    }


async def _authenticate_user(app: FastAPI, request: Request) -> None:
    try:
        await app.state.user_auth.authenticate(request.headers)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def _authenticate_internal(app: FastAPI, request: Request) -> None:
    try:
        await app.state.internal_auth.authenticate(request.headers)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def _run_master_task(app: FastAPI, request: BusinessTaskRequest) -> None:
    settings = app.state.settings
    stores: RuntimeStores = app.state.stores
    gateway_base_url = settings["gateway"]["base_url"]
    master_agent_id = settings["routing"]["master_agent_id"]
    await stores.runs.update(request.run_id, status="running")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{gateway_base_url}/a2a/{master_agent_id}/tasks",
                json=to_dict(request),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    run = await stores.runs.get(request.run_id)
                    if run and run.get("status") == "cancel_requested":
                        await stores.runs.update(request.run_id, status="cancelled")
                        return
                    await stores.events.append(request.conversation_id, parse_json_line(line))
        run = await stores.runs.get(request.run_id)
        if run and run.get("status") in {"cancel_requested", "cancelled"}:
            await stores.runs.update(request.run_id, status="cancelled")
            return
        await stores.runs.update(request.run_id, status="completed")
        await stores.events.append(request.conversation_id, agui_run_finished(request.run_id))
    except Exception as exc:  # pragma: no cover - exercised by integration tests.
        await stores.runs.update(request.run_id, status="failed", error=str(exc))
        await stores.events.append(request.conversation_id, agui_run_error(request.run_id, str(exc)))


async def _cancel_master_task(app: FastAPI, task_id: str) -> None:
    import httpx

    settings = app.state.settings
    gateway_base_url = settings["gateway"]["base_url"]
    master_agent_id = settings["routing"]["master_agent_id"]
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            await client.post(f"{gateway_base_url}/a2a/{master_agent_id}/tasks/{task_id}/cancel")
    except Exception:
        # Cancellation is best-effort. The run state remains cancel_requested.
        return


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:8000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
