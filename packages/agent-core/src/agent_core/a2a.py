from __future__ import annotations

from typing import Any

from fasta2a.schema import AgentCard, Skill, agent_card_ta


def build_agent_card(settings: dict[str, Any]) -> dict[str, Any]:
    agent = settings["agent"]
    display = agent.get("display", {})
    capabilities = agent.get("capabilities", [])
    server = settings.get("server", {})
    base_url = agent.get("url") or f"http://localhost:{server.get('port', 8000)}"
    card: AgentCard = {
        "name": str(display.get("label") or agent["id"]),
        "description": str(display.get("description") or f"{agent['id']} agent"),
        "url": str(base_url),
        "version": str(agent.get("version", "0.1.0")),
        "protocol_version": "0.3.0",
        "capabilities": {
            "streaming": True,
            "push_notifications": False,
            "state_transition_history": False,
        },
        "default_input_modes": ["application/json"],
        "default_output_modes": ["application/json"],
        "skills": [_build_skill(capability) for capability in capabilities],
    }
    return agent_card_ta.dump_python(card, by_alias=True)


def _build_skill(capability: dict[str, Any]) -> Skill:
    name = str(capability["name"])
    return {
        "id": name,
        "name": name.replace("_", " ").title(),
        "description": str(capability["description"]),
        "tags": [name],
        "input_modes": ["application/json"],
        "output_modes": ["application/json"],
    }
