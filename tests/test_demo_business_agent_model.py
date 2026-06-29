from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agents" / "demo-business-agent" / "src"))

import demo_business_agent.main as demo_main  # noqa: E402
from demo_business_agent.main import DemoBusinessResult  # noqa: E402


def test_demo_business_model_output_is_wrapped_in_result_envelope() -> None:
    result = DemoBusinessResult(summary="Model summary", items=["One", "Two"], ui_title="Model UI")
    envelope = demo_main._business_result_envelope(
        agent_id="demo_business_agent",
        run_id="run_1",
        task_id="task_1",
        result=result,
        bridge_result={"status": "completed"},
        attachments=[{"file_id": "file_1", "name": "demo.txt"}],
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
    app = SimpleNamespace(state=SimpleNamespace(settings=_model_settings(), pydantic_agent=pydantic_agent))

    result = asyncio.run(
        demo_main._generate_business_result(
            app,
            _payload(),
            bridge_result=None,
            attachments=[],
        )
    )

    assert result.summary == "Generated"


def test_demo_business_agent_falls_back_when_model_fails() -> None:
    app = SimpleNamespace(state=SimpleNamespace(settings=_model_settings(), pydantic_agent=FailingAgent()))

    result = asyncio.run(
        demo_main._generate_business_result(
            app,
            _payload(),
            bridge_result=None,
            attachments=[],
        )
    )

    assert result.summary == "Processed: hello"


def test_frontend_bridge_tool_uses_current_context() -> None:
    calls: list[tuple[object, dict[str, Any], str, dict[str, object], int]] = []

    async def fake_bridge_request(
        app: object,
        payload: dict[str, Any],
        action_name: str,
        args: dict[str, object],
        timeout_ms: int,
    ) -> dict[str, object]:
        calls.append((app, payload, action_name, args, timeout_ms))
        return {"status": "completed", "value": "ok"}

    original = demo_main._call_frontend_bridge_request
    demo_main._call_frontend_bridge_request = fake_bridge_request
    token = demo_main._bridge_context.set((object(), _payload()))
    try:
        result = asyncio.run(demo_main.call_frontend_bridge("get_selected_text", {"trim": True}, 1234))
    finally:
        demo_main._bridge_context.reset(token)
        demo_main._call_frontend_bridge_request = original

    assert result == {"status": "completed", "value": "ok"}
    assert calls[0][2:] == ("get_selected_text", {"trim": True}, 1234)


class FailingAgent:
    async def run(self, _prompt: str, *, output_type: object) -> object:
        raise RuntimeError("model failed")


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
