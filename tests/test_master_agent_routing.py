from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "master-agent" / "src"))

from master_agent.main import RouteDecision, _select_business_agent, _select_business_agent_with_model, _user_message_text  # noqa: E402


def test_master_agent_selects_best_capability_match() -> None:
    agents = [
        {
            "agent_id": "invoice_agent",
            "role": "business",
            "capabilities": [{"name": "invoice_review", "description": "Review invoices and payment terms."}],
        },
        {
            "agent_id": "contract_agent",
            "role": "business",
            "capabilities": [{"name": "contract_review", "description": "Analyze contracts and legal clauses."}],
        },
    ]

    assert _select_business_agent(agents, "please review this contract clause") == "contract_agent"


def test_master_agent_falls_back_to_first_business_agent() -> None:
    agents = [
        {"agent_id": "first_agent", "role": "business", "capabilities": []},
        {"agent_id": "second_agent", "role": "business", "capabilities": []},
    ]

    assert _select_business_agent(agents, "unmatched request") == "first_agent"


def test_master_agent_extracts_user_message_content() -> None:
    assert _user_message_text({"user_message": {"type": "text", "content": "hello"}}) == "hello"
    assert _user_message_text({"user_message": "hello"}) == "hello"


def test_master_agent_model_routing_selects_valid_agent() -> None:
    agents = [
        {"agent_id": "invoice_agent", "role": "business", "capabilities": []},
        {"agent_id": "contract_agent", "role": "business", "capabilities": []},
    ]
    agent = Agent(
        TestModel(
            custom_output_args={
                "target_agent_id": "contract_agent",
                "confidence": 0.9,
                "reason": "contract request",
            }
        )
    )

    selected = asyncio.run(
        _select_business_agent_with_model(
            agent,
            _model_settings(),
            agents,
            {"user_message": {"type": "text", "content": "review this"}},
        )
    )

    assert selected == "contract_agent"


def test_master_agent_invalid_model_route_falls_back_to_token_matching() -> None:
    agents = [
        {
            "agent_id": "invoice_agent",
            "role": "business",
            "capabilities": [{"name": "invoice_review", "description": "Review invoices."}],
        },
        {
            "agent_id": "contract_agent",
            "role": "business",
            "capabilities": [{"name": "contract_review", "description": "Review contracts."}],
        },
    ]
    agent = FakeAgent(RouteDecision(target_agent_id="missing_agent", confidence=0.9, reason="bad output"))

    selected = asyncio.run(
        _select_business_agent_with_model(
            agent,
            _model_settings(),
            agents,
            {"user_message": {"type": "text", "content": "review this contract"}},
        )
    )

    assert selected == "contract_agent"
    assert agent.calls == 1


class FakeAgent:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls = 0

    async def run(self, _prompt: str, *, output_type: object) -> object:
        self.calls += 1
        assert output_type is RouteDecision
        return SimpleNamespace(output=self.output)


def _model_settings() -> dict[str, object]:
    return {"llm": {"base_url": "https://api.openai.com/v1", "api_key": "test-key"}}


if __name__ == "__main__":
    test_master_agent_selects_best_capability_match()
    test_master_agent_falls_back_to_first_business_agent()
    test_master_agent_extracts_user_message_content()
    test_master_agent_model_routing_selects_valid_agent()
    test_master_agent_invalid_model_route_falls_back_to_token_matching()
    print("master agent routing tests ok")
