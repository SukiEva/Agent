from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "master-agent" / "src"))

from master_agent.main import _business_to_agui  # noqa: E402


def test_master_agent_passes_through_business_result_summary() -> None:
    events = asyncio.run(_collect_business_result_events("passthrough"))

    deltas = [event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"]
    assert deltas == ["Processed contract."]


def test_master_agent_summarizes_business_result_items() -> None:
    events = asyncio.run(_collect_business_result_events("summarize"))

    deltas = [event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"]
    assert deltas == ["Processed contract.\n\nSummary includes 2 result items."]


def test_master_agent_composes_business_result_items_and_warnings() -> None:
    events = asyncio.run(_collect_business_result_events("compose"))

    deltas = [event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"]
    assert deltas == ["Processed contract.\n- Clause A\n- Clause B\nWarnings:\n- Missing appendix"]


async def _collect_business_result_events(mode: str) -> list[dict[str, object]]:
    event = {
        "type": "business.result",
        "envelope": {
            "status": "completed",
            "agent_id": "demo_business_agent",
            "run_id": "run_1",
            "task_id": "task_1",
            "result_type": "demo_result.v1",
            "result": {
                "summary": "Processed contract.",
                "items": ["Clause A", "Clause B"],
            },
            "delivery": {
                "mode": mode,
                "final": True,
                "needs_master_summary": mode != "passthrough",
            },
            "warnings": ["Missing appendix"],
        },
    }
    return [agui_event async for agui_event in _business_to_agui(event)]


if __name__ == "__main__":
    test_master_agent_passes_through_business_result_summary()
    test_master_agent_summarizes_business_result_items()
    test_master_agent_composes_business_result_items_and_warnings()
    print("master agent delivery tests ok")
