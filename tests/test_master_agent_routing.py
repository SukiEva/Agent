from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "master-agent" / "src"))

from master_agent.main import _select_business_agent, _user_message_text  # noqa: E402


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


if __name__ == "__main__":
    test_master_agent_selects_best_capability_match()
    test_master_agent_falls_back_to_first_business_agent()
    test_master_agent_extracts_user_message_content()
    print("master agent routing tests ok")
