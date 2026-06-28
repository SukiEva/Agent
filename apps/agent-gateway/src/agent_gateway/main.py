from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent_core.config import load_service_config
from agent_core.logging import configure_service_logging
from agent_core.schemas.agent import AgentRef


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _load_registry() -> dict[str, AgentRef]:
    config = load_service_config(_conf_dir())
    registry_path = _conf_dir() / str(config.get("registry", {}).get("path", "agents.dev.yaml"))
    registry_config = load_service_config(registry_path.parent)
    # `load_service_config` reads default files; load the registry directly to avoid coupling it to service config.
    from agent_core.config import load_yaml_file

    registry_config = load_yaml_file(registry_path)
    agents: dict[str, AgentRef] = {}
    for raw_agent in registry_config.get("agents", []):
        agent = AgentRef(**_agent_with_defaults(raw_agent))
        agents[agent.agent_id] = agent
    return agents


def _settings() -> dict[str, Any]:
    return load_service_config(_conf_dir())


def _agent_with_defaults(raw_agent: dict[str, Any]) -> dict[str, Any]:
    display = raw_agent.get("display")
    if not display:
        display = {
            "label": raw_agent["agent_id"].replace("_", " ").title(),
            "description": f"{raw_agent['agent_id']} agent",
        }
    return {**raw_agent, "display": display}


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Gateway")
    app.state.settings = _settings()
    configure_service_logging(app.state.settings)
    app.state.registry = _load_registry()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agents")
    async def agents() -> list[dict[str, object]]:
        return [await _probe_agent(agent) for agent in app.state.registry.values()]

    @app.get("/agents/{agent_id}")
    async def agent(agent_id: str) -> dict[str, object]:
        agent_ref = app.state.registry.get(agent_id)
        if not agent_ref:
            raise HTTPException(status_code=404, detail="agent not found")
        return await _probe_agent(agent_ref)

    @app.post("/a2a/{agent_id}/tasks")
    async def create_task(agent_id: str, request: Request) -> StreamingResponse:
        agent_ref = app.state.registry.get(agent_id)
        if not agent_ref:
            raise HTTPException(status_code=404, detail="agent not found")
        payload = await request.json()

        async def stream():
            import httpx

            async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
                async with client.stream("POST", f"{agent_ref.base_url}/a2a/tasks", json=payload) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        yield body
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/a2a/{agent_id}/tasks/{task_id}/cancel")
    async def cancel_task(agent_id: str, task_id: str) -> dict[str, object]:
        agent_ref = app.state.registry.get(agent_id)
        if not agent_ref:
            raise HTTPException(status_code=404, detail="agent not found")
        import httpx

        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.post(f"{agent_ref.base_url}/a2a/tasks/{task_id}/cancel")
        return {"status": "cancel_requested", "downstream_status": response.status_code}

    return app


def _dump_agent(agent: AgentRef) -> dict[str, object]:
    if hasattr(agent, "model_dump"):
        return agent.model_dump(mode="json")
    return agent.dict()


async def _probe_agent(agent: AgentRef) -> dict[str, object]:
    dumped = _dump_agent(agent)
    card_url = dumped.get("card_url")
    if not card_url:
        return dumped
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(str(card_url))
            response.raise_for_status()
        card = response.json()
    except Exception as exc:
        dumped["healthy"] = False
        dumped["last_error"] = str(exc)
        return dumped

    dumped["healthy"] = True
    dumped["last_error"] = None
    dumped["metadata"] = {**dict(dumped.get("metadata") or {}), "agent_card": card}
    card_skills = _capabilities_from_agent_card(card)
    if card_skills:
        dumped["capabilities"] = card_skills
    return dumped


def _capabilities_from_agent_card(card: dict[str, Any]) -> list[dict[str, str]]:
    capabilities: list[dict[str, str]] = []
    for skill in card.get("skills", []) or []:
        if not isinstance(skill, dict):
            continue
        skill_id = skill.get("id") or skill.get("name")
        if not skill_id:
            continue
        capabilities.append(
            {
                "name": str(skill_id),
                "description": str(skill.get("description") or ""),
            }
        )
    return capabilities


app = create_app()


def main() -> None:
    import hypercorn.asyncio
    import hypercorn.config
    import asyncio

    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:8001"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
