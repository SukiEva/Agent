from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


@dataclass(frozen=True)
class OpenAICompatibleModelConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: int


def openai_compatible_config(settings: dict[str, Any]) -> OpenAICompatibleModelConfig:
    llm = settings.get("llm", {})
    if not isinstance(llm, dict):
        llm = {}
    return OpenAICompatibleModelConfig(
        base_url=str(llm.get("base_url", "https://api.openai.com/v1")),
        api_key=str(llm.get("api_key", "")),
        model=str(llm.get("model", "gpt-4.1-mini")),
        temperature=float(llm.get("temperature", 0.2)),
        timeout_seconds=int(llm.get("timeout_seconds", 60)),
    )


def build_openai_compatible_model(settings: dict[str, Any]) -> OpenAIChatModel:
    config = openai_compatible_config(settings)
    provider = OpenAIProvider(
        base_url=config.base_url,
        api_key=config.api_key or None,
        http_client=httpx.AsyncClient(timeout=config.timeout_seconds, trust_env=False),
    )
    return OpenAIChatModel(config.model, provider=provider)


def build_pydantic_agent(settings: dict[str, Any], *, system_prompt: str = "") -> Agent:
    config = openai_compatible_config(settings)
    return Agent(
        build_openai_compatible_model(settings),
        system_prompt=system_prompt,
        defer_model_check=True,
        model_settings={"temperature": config.temperature},
    )
