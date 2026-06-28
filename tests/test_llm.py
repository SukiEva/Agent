from __future__ import annotations

import sys
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from agent_core.config import validate_service_config
from agent_core.llm import build_openai_compatible_model, build_pydantic_agent, openai_compatible_config


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "demo-business-agent" / "src"))
sys.path.append(str(ROOT / "apps" / "agents" / "master-agent" / "src"))


def test_openai_compatible_config_is_validated_and_builds_pydantic_ai_objects() -> None:
    settings = validate_service_config(
        {
            "llm": {
                "base_url": "http://llm.example.test/v1",
                "api_key": "secret",
                "model": "demo-model",
                "temperature": 0.1,
                "timeout_seconds": 5,
            }
        }
    )

    config = openai_compatible_config(settings)
    assert config.base_url == "http://llm.example.test/v1"
    assert config.model == "demo-model"
    assert config.temperature == 0.1

    model = build_openai_compatible_model(settings)
    assert isinstance(model, OpenAIChatModel)

    agent = build_pydantic_agent(settings, system_prompt="test")
    assert isinstance(agent, Agent)


def test_agent_apps_create_pydantic_ai_agents() -> None:
    from demo_business_agent.main import create_app as create_demo_app
    from master_agent.main import create_app as create_master_app

    assert isinstance(create_demo_app().state.pydantic_agent, Agent)
    assert isinstance(create_master_app().state.pydantic_agent, Agent)


if __name__ == "__main__":
    test_openai_compatible_config_is_validated_and_builds_pydantic_ai_objects()
    test_agent_apps_create_pydantic_ai_agents()
    print("llm tests ok")
