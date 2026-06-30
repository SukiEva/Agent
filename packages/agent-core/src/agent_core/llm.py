from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class OpenAICompatibleModelConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: int
    required: bool


def openai_compatible_config(settings: dict[str, Any]) -> OpenAICompatibleModelConfig:
    llm = settings.get("llm", {})
    if not isinstance(llm, dict):
        llm = {}
    return OpenAICompatibleModelConfig(
        base_url=str(llm.get("base_url", DEFAULT_OPENAI_BASE_URL)),
        api_key=str(llm.get("api_key", "")),
        model=str(llm.get("model", "gpt-4.1-mini")),
        temperature=float(llm.get("temperature", 0.2)),
        timeout_seconds=int(llm.get("timeout_seconds", 60)),
        required=bool(llm.get("required", False)),
    )


def should_execute_model(settings: dict[str, Any]) -> bool:
    config = openai_compatible_config(settings)
    return (
        config.required
        or config.model == "test"
        or bool(config.api_key)
        or config.base_url.rstrip("/") != DEFAULT_OPENAI_BASE_URL
    )


def model_fallback_allowed(settings: dict[str, Any]) -> bool:
    return not openai_compatible_config(settings).required


def build_openai_compatible_model(settings: dict[str, Any]) -> Model[Any]:
    config = openai_compatible_config(settings)
    if config.model == "test":
        return TestModel()
    if config.required and not config.api_key and config.base_url.rstrip("/") == DEFAULT_OPENAI_BASE_URL:
        raise ValueError("OPENAI_API_KEY is required when llm.required is true")
    provider = OpenAIProvider(
        base_url=config.base_url,
        api_key=config.api_key or None,
        http_client=httpx.AsyncClient(timeout=config.timeout_seconds, trust_env=False),
    )
    return OpenAIChatModel(config.model, provider=provider)


def build_pydantic_agent(settings: dict[str, Any], *, system_prompt: str = "") -> Agent:
    config = openai_compatible_config(settings)
    return Agent(
        _build_agent_model(settings, system_prompt=system_prompt),
        system_prompt=system_prompt,
        defer_model_check=True,
        model_settings={"temperature": config.temperature},
    )


def _build_agent_model(settings: dict[str, Any], *, system_prompt: str) -> Model[Any]:
    config = openai_compatible_config(settings)
    if config.model != "test":
        return build_openai_compatible_model(settings)
    if "Route" in system_prompt or "route" in system_prompt:
        return TestModel(
            call_tools=[],
            custom_output_args={
                "target_agent_id": "demo_business_agent",
                "confidence": 0.95,
                "reason": "Local test model routes to the demo business agent.",
            }
        )
    return TestModel(
        call_tools=[],
        custom_output_args={
            "summary": "Local test model generated a demo business result.",
            "items": ["PydanticAI model path executed", "Structured output was validated"],
            "ui_title": "Model Result",
        }
    )
