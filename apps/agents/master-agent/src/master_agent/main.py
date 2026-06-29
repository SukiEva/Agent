from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_core.a2a import build_agent_card
from agent_core.config import load_service_config
from agent_core.events import (
    agui_custom,
    agui_text_delta,
    agui_text_end,
    agui_text_start,
)
from agent_core.ids import new_message_id
from agent_core.llm import build_pydantic_agent, should_execute_model
from agent_core.logging import configure_service_logging
from agent_core.serialization import json_line, parse_json_line
from agent_core.server import hypercorn_bind
from agent_core.stores import create_runtime_stores


class RouteDecision(BaseModel):
    target_agent_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _settings() -> dict[str, Any]:
    return load_service_config(_conf_dir())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _start_command_listener(app)
    try:
        yield
    finally:
        await _stop_command_listener(app)


def create_app() -> FastAPI:
    app = FastAPI(title="Master Agent", lifespan=lifespan)
    app.state.settings = _settings()
    configure_service_logging(app.state.settings)
    app.state.pydantic_agent = build_pydantic_agent(
        app.state.settings,
        system_prompt="Route the user's task to the best available business agent.",
    )
    app.state.stores = create_runtime_stores(app.state.settings)
    app.state.cancelled_tasks = set()
    app.state.active_targets = {}

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
            task_id = str(payload["task_id"])
            target_agent_id = await _choose_business_agent(app, payload)
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


async def _choose_business_agent(app: FastAPI, payload: dict[str, Any]) -> str | None:
    selected_agent_id = payload.get("selected_agent_id")
    if selected_agent_id:
        return str(selected_agent_id)
    agents = await _load_business_agents(app)
    return await _select_business_agent_with_model(app.state.pydantic_agent, app.state.settings, agents, payload)


async def _select_business_agent_with_model(
    agent: Any,
    settings: dict[str, Any],
    agents: list[dict[str, Any]],
    payload: dict[str, Any],
) -> str | None:
    if should_execute_model(settings):
        decision = await _route_with_model(agent, agents, payload)
        if decision and _is_valid_agent_id(decision.target_agent_id, agents):
            return decision.target_agent_id
    return _select_business_agent(agents, _user_message_text(payload))


async def _route_with_model(agent: Any, agents: list[dict[str, Any]], payload: dict[str, Any]) -> RouteDecision | None:
    if not agents:
        return None
    try:
        result = await agent.run(_route_prompt(agents, payload), output_type=RouteDecision)
        output = _agent_output(result)
        if isinstance(output, RouteDecision):
            return output
        if isinstance(output, dict):
            return RouteDecision(**output)
        return RouteDecision.model_validate(output)
    except Exception:
        return None


def _route_prompt(agents: list[dict[str, Any]], payload: dict[str, Any]) -> str:
    candidates = [
        {
            "agent_id": agent.get("agent_id"),
            "display": agent.get("display", {}),
            "capabilities": agent.get("capabilities", []),
            "healthy": agent.get("healthy", True),
        }
        for agent in agents
    ]
    request = {
        "user_message": _user_message_text(payload),
        "attachments": payload.get("attachments", []),
        "business_agents": candidates,
    }
    return (
        "Choose exactly one business agent for this user task. "
        "Return only the structured RouteDecision fields requested by the output schema.\n\n"
        f"{json.dumps(request, ensure_ascii=False, separators=(',', ':'))}"
    )


def _agent_output(result: Any) -> Any:
    for attr in ("output", "data"):
        if hasattr(result, attr):
            return getattr(result, attr)
    return result


def _is_valid_agent_id(agent_id: str, agents: list[dict[str, Any]]) -> bool:
    return agent_id in {str(agent["agent_id"]) for agent in agents}


async def _load_business_agents(app: FastAPI) -> list[dict[str, Any]]:
    import httpx

    gateway_base_url = app.state.settings["gateway"]["base_url"]
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(f"{gateway_base_url}/agents")
        response.raise_for_status()
    return [
        agent
        for agent in response.json()
        if agent.get("role") == "business" and agent.get("visibility") == "public" and agent.get("healthy", True)
    ]


def _select_business_agent(agents: list[dict[str, Any]], user_message: str) -> str | None:
    if not agents:
        return None
    message_tokens = _tokens(user_message)
    scored = [(_agent_match_score(agent, message_tokens), index, agent) for index, agent in enumerate(agents)]
    best_score, _, best_agent = max(scored, key=lambda item: (item[0], -item[1]))
    if best_score > 0:
        return str(best_agent["agent_id"])
    return str(agents[0]["agent_id"])


def _agent_match_score(agent: dict[str, Any], message_tokens: set[str]) -> int:
    agent_tokens = _tokens(str(agent.get("agent_id", "")))
    display = agent.get("display") or {}
    if isinstance(display, dict):
        agent_tokens |= _tokens(str(display.get("label", "")))
        agent_tokens |= _tokens(str(display.get("description", "")))
    for capability in agent.get("capabilities", []) or []:
        if not isinstance(capability, dict):
            continue
        agent_tokens |= _tokens(str(capability.get("name", "")))
        agent_tokens |= _tokens(str(capability.get("description", "")))
    return len(message_tokens & agent_tokens)


def _tokens(text: str) -> set[str]:
    return {token for token in text.lower().replace("_", " ").replace("-", " ").split() if len(token) >= 3}


def _user_message_text(payload: dict[str, Any]) -> str:
    message = payload.get("user_message")
    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            return str(content)
    return str(message or "")


async def _cancel_business_task(app: FastAPI, target_agent_id: str, task_id: str) -> None:
    import httpx

    gateway_base_url = app.state.settings["gateway"]["base_url"]
    await app.state.stores.commands.publish(target_agent_id, {"type": "cancel_task", "task_id": task_id})
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            await client.post(f"{gateway_base_url}/a2a/{target_agent_id}/tasks/{task_id}/cancel")
    except Exception:
        return


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
        if command.get("type") != "cancel_task":
            continue
        task_id = str(command["task_id"])
        app.state.cancelled_tasks.add(task_id)
        target_agent_id = app.state.active_targets.get(task_id)
        if target_agent_id:
            await _cancel_business_task(app, target_agent_id, task_id)


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
        message_id = new_message_id()
        summary = _business_result_text(envelope)
        yield agui_text_start(message_id)
        yield agui_text_delta(message_id, summary)
        yield agui_text_end(message_id)
        ui = envelope.get("ui")
        if ui:
            yield agui_custom("ui.component.render", ui)
        return

    if event_type == "business.error":
        yield agui_custom("business.error", event)


def _business_result_text(envelope: dict[str, Any]) -> str:
    result = envelope.get("result", {})
    if not isinstance(result, dict):
        return "Business task completed."
    summary = str(result.get("summary") or "Business task completed.")
    delivery = envelope.get("delivery", {})
    mode = delivery.get("mode") if isinstance(delivery, dict) else "summarize"
    if mode == "passthrough":
        return summary
    if mode == "compose":
        return _compose_business_result(summary, result, envelope)
    return _summarize_business_result(summary, result)


def _summarize_business_result(summary: str, result: dict[str, Any]) -> str:
    items = result.get("items")
    if isinstance(items, list) and items:
        item_count = len(items)
        return f"{summary}\n\nSummary includes {item_count} result item{'s' if item_count != 1 else ''}."
    return summary


def _compose_business_result(summary: str, result: dict[str, Any], envelope: dict[str, Any]) -> str:
    lines = [summary]
    items = result.get("items")
    if isinstance(items, list) and items:
        lines.extend(f"- {item}" for item in items)
    warnings = envelope.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(str(line) for line in lines)


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = hypercorn_bind(app.state.settings)
    asyncio.run(hypercorn.asyncio.serve(app, config))
