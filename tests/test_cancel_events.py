from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from agent_core.business_app import BusinessTaskContext


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "demo-business-agent" / "src"))

import demo_business_agent.main as demo_main  # noqa: E402


def test_demo_cancelled_event_shape() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings={"agent": {"id": "demo_business_agent"}},
            cancelled_tasks=set(),
        )
    )
    context = BusinessTaskContext(
        demo_main.business,
        app,
        {
            "conversation_id": "conv_1",
            "run_id": "run_1",
            "task_id": "task_1",
            "client_id": "client_1",
            "user_message": {"type": "text", "content": "cancel"},
        },
    )
    event = context.cancelled_event()
    assert event["type"] == "business.error"
    assert event["agent_id"] == "demo_business_agent"
    assert event["run_id"] == "run_1"
    assert event["task_id"] == "task_1"
    assert event["error"]["code"] == "TASK_CANCELLED"
    assert event["error"]["cancelled"] is True
    assert event["error"]["recoverable"] is True


if __name__ == "__main__":
    test_demo_cancelled_event_shape()
    print("cancel event tests ok")
