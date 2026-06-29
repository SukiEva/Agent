from __future__ import annotations

import sys
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from agent_core.config import validate_service_config
from agent_core.llm import build_openai_compatible_model, build_pydantic_agent, openai_compatible_config, should_execute_model


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


def test_model_execution_is_enabled_only_with_credentials_or_custom_endpoint() -> None:
    assert should_execute_model({"llm": {"base_url": "https://api.openai.com/v1", "api_key": ""}}) is False
    assert should_execute_model({"llm": {"base_url": "https://api.openai.com/v1", "api_key": "", "model": "test"}}) is True
    assert should_execute_model({"llm": {"base_url": "https://api.openai.com/v1", "api_key": "secret"}}) is True
    assert should_execute_model({"llm": {"base_url": "http://localhost:11434/v1", "api_key": ""}}) is True


def test_local_test_model_builds_pydantic_ai_agent_without_external_endpoint() -> None:
    settings = validate_service_config({"llm": {"model": "test", "api_key": ""}})

    model = build_openai_compatible_model(settings)
    assert isinstance(model, TestModel)

    agent = build_pydantic_agent(settings, system_prompt="Route the user's task.")
    assert isinstance(agent, Agent)


if __name__ == "__main__":
    test_openai_compatible_config_is_validated_and_builds_pydantic_ai_objects()
    test_agent_apps_create_pydantic_ai_agents()
    test_model_execution_is_enabled_only_with_credentials_or_custom_endpoint()
    test_local_test_model_builds_pydantic_ai_agent_without_external_endpoint()
    print("llm tests ok")
