from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agent_core.business_app import BusinessTaskContext, _bridge_context


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "demo-business-agent" / "src"))

import demo_business_agent.main as demo_main  # noqa: E402
from demo_business_agent.main import DemoBusinessResult  # noqa: E402


def test_demo_business_model_output_is_wrapped_in_result_envelope() -> None:
    result = DemoBusinessResult(summary="Model summary", items=["One", "Two"], ui_title="Model UI")
    ctx = _context()
    ctx.bridge_result = {"status": "completed"}
    envelope = ctx.result(
        summary=result.summary,
        items=result.items,
        ui_title=result.ui_title,
        ui_props={
            "title": result.ui_title,
            "summary": result.summary,
            "items": result.items,
            "attachments": [{"file_id": "file_1", "name": "demo.txt"}],
        },
    )

    assert envelope.result["summary"] == "Model summary"
    assert envelope.result["items"] == ["One", "Two"]
    assert envelope.ui is not None
    assert envelope.ui.component == "demo.result_card"
    assert envelope.ui.props["title"] == "Model UI"


def test_demo_business_agent_calls_model_when_enabled() -> None:
    pydantic_agent = Agent(
        TestModel(custom_output_args={"summary": "Generated", "items": ["A"], "ui_title": "Generated UI"})
    )
    original_agent = demo_main.business.pydantic
    demo_main.business.pydantic = pydantic_agent

    try:
        result = asyncio.run(_context(settings=_model_settings()).run_model("generate"))
    finally:
        demo_main.business.pydantic = original_agent

    assert result.summary == "Generated"


def test_demo_business_agent_falls_back_when_model_fails() -> None:
    original_agent = demo_main.business.pydantic
    demo_main.business.pydantic = FailingAgent()

    try:
        result = asyncio.run(_context(settings=_model_settings()).run_model("generate"))
    finally:
        demo_main.business.pydantic = original_agent

    assert result.summary == "Processed: hello"


def test_frontend_bridge_tool_uses_current_context() -> None:
    context = FakeBridgeContext()
    token = _bridge_context.set(context)
    try:
        result = asyncio.run(demo_main.call_frontend_bridge("get_selected_text", {"trim": True}, 1234))
    finally:
        _bridge_context.reset(token)

    assert result == {"status": "completed", "value": "ok"}
    assert context.calls == [("get_selected_text", {"trim": True}, 1234)]


class FailingAgent:
    async def run(self, _prompt: str, *, output_type: object) -> object:
        raise RuntimeError("model failed")


class FakeBridgeContext:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], int]] = []

    async def frontend_bridge(
        self,
        action_name: str,
        args: dict[str, object],
        timeout_ms: int,
    ) -> dict[str, object]:
        self.calls.append((action_name, args, timeout_ms))
        return {"status": "completed", "value": "ok"}


def _context(settings: dict[str, object] | None = None) -> BusinessTaskContext[DemoBusinessResult]:
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=settings or {"agent": {"id": "demo_business_agent"}},
            cancelled_tasks=set(),
        )
    )
    return BusinessTaskContext(demo_main.business, app, _payload())


def _payload() -> dict[str, Any]:
    return {
        "conversation_id": "conv_1",
        "run_id": "run_1",
        "task_id": "task_1",
        "client_id": "client_1",
        "user_message": {"type": "text", "content": "hello"},
        "attachments": [],
        "context": {},
    }


def _model_settings() -> dict[str, object]:
    return {"llm": {"base_url": "https://api.openai.com/v1", "api_key": "test-key"}}


if __name__ == "__main__":
    test_demo_business_model_output_is_wrapped_in_result_envelope()
    test_demo_business_agent_calls_model_when_enabled()
    test_demo_business_agent_falls_back_when_model_fails()
    test_frontend_bridge_tool_uses_current_context()
    print("demo business agent model tests ok")
