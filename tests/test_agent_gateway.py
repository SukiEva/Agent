from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "apps" / "agent-gateway" / "src"))

from agent_core.schemas.agent import AgentRef  # noqa: E402
from agent_gateway.main import _probe_agent, create_app  # noqa: E402


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
    calls = 0

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _url: str) -> FakeResponse:
        self.__class__.calls += 1
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


class FakeStreamResponse:
    status_code = 200
    body = b""
    chunks: list[bytes] = []
    headers = {"content-type": "application/x-ndjson"}
    reason_phrase = "OK"

    def __init__(self) -> None:
        self.closed = False

    async def aread(self) -> bytes:
        return self.body

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class FakeRoutingAsyncClient:
    response = FakeStreamResponse
    closed = False

    def __init__(self, **_kwargs: object) -> None:
        self.response_instance = self.response()

    def build_request(self, method: str, url: str, json: dict[str, object]) -> dict[str, object]:
        return {"method": method, "url": url, "json": json}

    async def send(self, _request: dict[str, object], stream: bool = False) -> FakeStreamResponse:
        assert stream is True
        return self.response_instance

    async def aclose(self) -> None:
        self.__class__.closed = True


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


def test_create_task_streams_downstream_response() -> None:
    import httpx

    class OkResponse(FakeStreamResponse):
        status_code = 200
        chunks = [b'{"type":"one"}\n', b'{"type":"two"}\n']

    FakeRoutingAsyncClient.response = OkResponse
    FakeRoutingAsyncClient.closed = False
    original = httpx.AsyncClient
    httpx.AsyncClient = FakeRoutingAsyncClient  # type: ignore[assignment]
    try:
        app = create_app()
        app.state.registry = {
            "demo_business_agent": AgentRef(agent_id="demo_business_agent", role="business", base_url="http://agent")
        }
        response = TestClient(app).post("/a2a/demo_business_agent/tasks", json={"task_id": "task_1"})
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.text == '{"type":"one"}\n{"type":"two"}\n'
    assert FakeRoutingAsyncClient.closed is True


def test_create_task_preserves_downstream_error_status() -> None:
    import httpx

    class ErrorResponse(FakeStreamResponse):
        status_code = 503
        body = b"agent unavailable"
        reason_phrase = "Service Unavailable"

    FakeRoutingAsyncClient.response = ErrorResponse
    FakeRoutingAsyncClient.closed = False
    original = httpx.AsyncClient
    httpx.AsyncClient = FakeRoutingAsyncClient  # type: ignore[assignment]
    try:
        app = create_app()
        app.state.registry = {
            "demo_business_agent": AgentRef(agent_id="demo_business_agent", role="business", base_url="http://agent")
        }
        response = TestClient(app).post("/a2a/demo_business_agent/tasks", json={"task_id": "task_1"})
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]

    assert response.status_code == 503
    assert response.json()["detail"] == "agent unavailable"
    assert FakeRoutingAsyncClient.closed is True


def test_agents_endpoint_caches_agent_card_probe() -> None:
    import httpx

    original = httpx.AsyncClient
    FakeAsyncClient.error = None
    FakeAsyncClient.calls = 0
    FakeAsyncClient.payload = {
        "name": "Demo Business Agent",
        "skills": [{"id": "demo_task", "description": "Runs a demo task."}],
    }
    httpx.AsyncClient = FakeAsyncClient  # type: ignore[assignment]
    try:
        app = create_app()
        app.state.settings["registry"]["probe_cache_ttl_seconds"] = 60
        app.state.registry = {
            "demo_business_agent": AgentRef(
                agent_id="demo_business_agent",
                role="business",
                base_url="http://agent",
                card_url="http://agent/.well-known/agent-card.json",
            )
        }
        client = TestClient(app)
        first = client.get("/agents")
        second = client.get("/agents")
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert FakeAsyncClient.calls == 1


def test_agents_endpoint_can_disable_agent_card_probe_cache() -> None:
    import httpx

    original = httpx.AsyncClient
    FakeAsyncClient.error = None
    FakeAsyncClient.calls = 0
    FakeAsyncClient.payload = {
        "name": "Demo Business Agent",
        "skills": [{"id": "demo_task", "description": "Runs a demo task."}],
    }
    httpx.AsyncClient = FakeAsyncClient  # type: ignore[assignment]
    try:
        app = create_app()
        app.state.settings["registry"]["probe_cache_ttl_seconds"] = 0
        app.state.registry = {
            "demo_business_agent": AgentRef(
                agent_id="demo_business_agent",
                role="business",
                base_url="http://agent",
                card_url="http://agent/.well-known/agent-card.json",
            )
        }
        client = TestClient(app)
        client.get("/agents")
        client.get("/agents")
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]

    assert FakeAsyncClient.calls == 2


if __name__ == "__main__":
    test_probe_agent_enriches_capabilities_from_agent_card()
    test_probe_agent_marks_unhealthy_on_card_failure()
    test_create_task_streams_downstream_response()
    test_create_task_preserves_downstream_error_status()
    test_agents_endpoint_caches_agent_card_probe()
    test_agents_endpoint_can_disable_agent_card_probe_cache()
    print("agent gateway tests ok")
