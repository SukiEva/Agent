from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agent-gateway" / "src"))

from agent_core.schemas.agent import AgentRef  # noqa: E402
from agent_gateway.main import _probe_agent  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class FakeAsyncClient:
    payload: dict[str, object] = {}
    error: Exception | None = None

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _url: str) -> FakeResponse:
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


def test_probe_agent_enriches_capabilities_from_agent_card() -> None:
    asyncio.run(_test_probe_agent_enriches_capabilities_from_agent_card())


async def _test_probe_agent_enriches_capabilities_from_agent_card() -> None:
    import httpx

    original = httpx.AsyncClient
    FakeAsyncClient.error = None
    FakeAsyncClient.payload = {
        "name": "Demo Business Agent",
        "skills": [{"id": "demo_task", "description": "Runs a demo task."}],
    }
    httpx.AsyncClient = FakeAsyncClient  # type: ignore[assignment]
    try:
        agent = AgentRef(
            agent_id="demo_business_agent",
            role="business",
            base_url="http://localhost:8011",
            card_url="http://localhost:8011/.well-known/agent-card.json",
        )
        dumped = await _probe_agent(agent)
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]

    assert dumped["healthy"] is True
    assert dumped["last_error"] is None
    assert dumped["capabilities"] == [{"name": "demo_task", "description": "Runs a demo task."}]
    assert dumped["metadata"]["agent_card"]["name"] == "Demo Business Agent"


def test_probe_agent_marks_unhealthy_on_card_failure() -> None:
    asyncio.run(_test_probe_agent_marks_unhealthy_on_card_failure())


async def _test_probe_agent_marks_unhealthy_on_card_failure() -> None:
    import httpx

    original = httpx.AsyncClient
    FakeAsyncClient.error = RuntimeError("card unavailable")
    httpx.AsyncClient = FakeAsyncClient  # type: ignore[assignment]
    try:
        agent = AgentRef(
            agent_id="demo_business_agent",
            role="business",
            base_url="http://localhost:8011",
            card_url="http://localhost:8011/.well-known/agent-card.json",
        )
        dumped = await _probe_agent(agent)
    finally:
        FakeAsyncClient.error = None
        httpx.AsyncClient = original  # type: ignore[assignment]

    assert dumped["healthy"] is False
    assert "card unavailable" in str(dumped["last_error"])


if __name__ == "__main__":
    test_probe_agent_enriches_capabilities_from_agent_card()
    test_probe_agent_marks_unhealthy_on_card_failure()
    print("agent gateway tests ok")
