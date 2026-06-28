from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "demo-business-agent" / "src"))

from demo_business_agent.main import _cancelled_event  # noqa: E402


def test_demo_cancelled_event_shape() -> None:
    event = _cancelled_event("demo_business_agent", "run_1", "task_1")
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
