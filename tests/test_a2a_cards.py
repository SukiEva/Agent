from __future__ import annotations

from fastapi.testclient import TestClient
from fasta2a.schema import agent_card_ta

from agent_core.a2a import build_agent_card
from demo_business_agent.main import create_app as create_demo_app
from master_agent.main import create_app as create_master_app


def test_build_agent_card_uses_fasta2a_schema() -> None:
    card = build_agent_card(
        {
            "server": {"port": 8011},
            "agent": {
                "id": "demo_business_agent",
                "display": {"label": "Demo Business Agent", "description": "Demo description."},
                "capabilities": [{"name": "demo_task", "description": "Runs a fake task."}],
            },
        }
    )

    agent_card_ta.validate_python(card)
    assert card["protocolVersion"] == "0.3.0"
    assert card["url"] == "http://localhost:8011"
    assert card["capabilities"]["streaming"] is True
    assert card["skills"][0]["id"] == "demo_task"
    assert card["skills"][0]["inputModes"] == ["application/json"]


def test_agent_services_expose_standard_agent_cards() -> None:
    for create_app in (create_master_app, create_demo_app):
        response = TestClient(create_app()).get("/.well-known/agent-card.json")
        assert response.status_code == 200
        card = response.json()
        agent_card_ta.validate_python(card)
        assert "protocolVersion" in card
        assert "defaultInputModes" in card


if __name__ == "__main__":
    test_build_agent_card_uses_fasta2a_schema()
    test_agent_services_expose_standard_agent_cards()
    print("a2a card tests ok")
