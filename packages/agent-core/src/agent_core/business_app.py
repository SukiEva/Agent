from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Generic, Literal, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_ai import Agent

from agent_core.a2a import build_agent_card
from agent_core.auth import build_internal_auth_headers
from agent_core.config import load_service_config
from agent_core.llm import build_pydantic_agent, model_fallback_allowed, should_execute_model
from agent_core.logging import configure_service_logging
from agent_core.schemas.business import BusinessProgressEvent, BusinessResultEnvelope, DeliveryDirective
from agent_core.schemas.errors import AgentError
from agent_core.schemas.ui import UiDescriptor, UiFallback
from agent_core.serialization import json_line, to_dict
from agent_core.stores import create_runtime_stores


OutputT = TypeVar("OutputT", bound=BaseModel)
TaskHandler = Callable[["BusinessTaskContext[Any]"], Awaitable[BusinessResultEnvelope]]

_bridge_context: ContextVar["BusinessTaskContext[Any] | None"] = ContextVar("business_bridge_context", default=None)


@dataclass
class BusinessAgentApp(Generic[OutputT]):
    title: str
    conf_dir: Path
    result_type: str
    ui_component: str
    output_type: type[OutputT]
    system_prompt: str
    fallback_factory: Callable[["BusinessTaskContext[OutputT]"], OutputT]
    task_handler: TaskHandler | None = None
    pydantic: Agent = field(init=False)
    settings: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.settings = load_service_config(self.conf_dir)
        self.pydantic = build_pydantic_agent(self.settings, system_prompt=self.system_prompt)
        self.pydantic.tool_plain(
            self.call_frontend_bridge,
            name="call_frontend_bridge",
            description="Call a frontend bridge function in the user's active browser session.",
        )

    def task(self, handler: TaskHandler) -> TaskHandler:
        self.task_handler = handler
        return handler

    def create_app(self) -> FastAPI:
        business = self

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            business._start_command_listener(app)
            try:
                yield
            finally:
                await business._stop_command_listener(app)

        app = FastAPI(title=self.title, lifespan=lifespan)
        app.state.settings = self.settings
        configure_service_logging(app.state.settings)
        app.state.pydantic_agent = self.pydantic
        app.state.stores = create_runtime_stores(app.state.settings)
        app.state.cancelled_tasks = set()

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/.well-known/agent-card.json")
        async def agent_card() -> dict[str, object]:
            return build_agent_card(app.state.settings)

        @app.post("/a2a/tasks")
        async def create_task(request: Request) -> StreamingResponse:
            payload = await request.json()

            async def stream():
                context = BusinessTaskContext(business=business, app=app, payload=payload)
                async for event in business._run_task(context):
                    yield json_line(event)

            return StreamingResponse(stream(), media_type="application/x-ndjson")

        @app.post("/a2a/tasks/{task_id}/cancel")
        async def cancel_task(task_id: str) -> dict[str, object]:
            app.state.cancelled_tasks.add(task_id)
            return {"status": "cancel_requested", "task_id": task_id}

        return app

    async def call_frontend_bridge(
        self,
        action_name: str,
        args: dict[str, object],
        timeout_ms: int = 30000,
    ) -> dict[str, object]:
        context = _bridge_context.get()
        if context is None:
            return {"status": "unavailable", "error": "frontend bridge context is not available"}
        return await context.frontend_bridge(action_name, args, timeout_ms)

    async def _run_task(self, context: "BusinessTaskContext[OutputT]") -> AsyncIterator[dict[str, object]]:
        for message in context.progress_messages:
            if context.is_cancelled():
                yield context.cancelled_event()
                return
            await asyncio.sleep(context.delay_ms / 1000)
            if context.is_cancelled():
                yield context.cancelled_event()
                return
            yield to_dict(context.progress(message))

        if context.is_cancelled():
            yield context.cancelled_event()
            return
        handler = self.task_handler
        if handler is None:
            raise RuntimeError(f"business agent {self.title} has no task handler")
        token = _bridge_context.set(context)
        try:
            try:
                envelope = await handler(context)
            except Exception as exc:
                yield context.error_event("MODEL_TASK_FAILED", str(exc), recoverable=False, retryable=True)
                return
        finally:
            _bridge_context.reset(token)
        if context.is_cancelled():
            yield context.cancelled_event()
            return
        yield to_dict(context.progress(context.final_progress_message, status="completed"))
        yield {"type": "business.result", "envelope": to_dict(envelope)}

    def _start_command_listener(self, app: FastAPI) -> None:
        if app.state.settings.get("runtime", {}).get("store") != "redis":
            app.state.command_listener = None
            return
        app.state.command_listener = asyncio.create_task(self._listen_for_commands(app))

    async def _stop_command_listener(self, app: FastAPI) -> None:
        listener = getattr(app.state, "command_listener", None)
        if listener is None:
            return
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            return

    async def _listen_for_commands(self, app: FastAPI) -> None:
        agent_id = app.state.settings["agent"]["id"]
        async for command in app.state.stores.commands.stream(agent_id):
            if command.get("type") == "cancel_task":
                app.state.cancelled_tasks.add(str(command["task_id"]))


@dataclass
class BusinessTaskContext(Generic[OutputT]):
    business: BusinessAgentApp[OutputT]
    app: FastAPI
    payload: dict[str, Any]
    bridge_result: dict[str, object] | None = None

    @property
    def agent_id(self) -> str:
        return str(self.app.state.settings["agent"]["id"])

    @property
    def run_id(self) -> str:
        return str(self.payload["run_id"])

    @property
    def task_id(self) -> str:
        return str(self.payload["task_id"])

    @property
    def delay_ms(self) -> int:
        return int(self.payload.get("context", {}).get("demo_delay_ms", 100))

    @property
    def progress_messages(self) -> list[str]:
        return [
            "Demo agent accepted the task.",
            "Demo agent is preparing a component descriptor.",
            "Demo agent is generating the business result.",
        ]

    @property
    def final_progress_message(self) -> str:
        return "Demo agent completed the business result."

    @property
    def attachments(self) -> list[dict[str, object]]:
        raw_attachments = self.payload.get("attachments", [])
        if not isinstance(raw_attachments, list):
            return []
        summaries: list[dict[str, object]] = []
        for attachment in raw_attachments:
            if not isinstance(attachment, dict) or "file_id" not in attachment:
                continue
            summaries.append(
                {
                    "file_id": str(attachment["file_id"]),
                    "name": str(attachment.get("name") or ""),
                    "mime_type": attachment.get("mime_type"),
                    "size_bytes": attachment.get("size_bytes"),
                }
            )
        return summaries

    @property
    def user_message_text(self) -> str:
        message = self.payload.get("user_message")
        if isinstance(message, dict):
            content = message.get("content")
            if content is not None:
                return str(content)
        return str(message or "")

    @property
    def agent(self) -> Agent:
        return self.business.pydantic

    def is_cancelled(self) -> bool:
        return self.task_id in self.app.state.cancelled_tasks

    def progress(self, message: str, *, status: Literal["running", "completed"] = "running") -> BusinessProgressEvent:
        return BusinessProgressEvent(
            agent_id=self.agent_id,
            run_id=self.run_id,
            task_id=self.task_id,
            message=message,
            status=status,
        )

    async def maybe_frontend_bridge(self) -> dict[str, object] | None:
        bridge = self.payload.get("context", {}).get("bridge")
        if not isinstance(bridge, dict) or not bridge.get("enabled"):
            return None
        action_name = str(bridge.get("action_name", "get_selected_text"))
        args = bridge.get("args") if isinstance(bridge.get("args"), dict) else {}
        self.bridge_result = await self.frontend_bridge(action_name, args, int(bridge.get("timeout_ms", 30000)))
        return self.bridge_result

    async def frontend_bridge(
        self,
        action_name: str,
        args: dict[str, object],
        timeout_ms: int = 30000,
    ) -> dict[str, object]:
        import httpx

        agent_server_base_url = self.app.state.settings.get("agent_server", {}).get("base_url", "http://localhost:8000")
        headers = build_internal_auth_headers(
            self.app.state.settings,
            service_id=self.agent_id,
            agent_id=self.agent_id,
        )
        async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
            response = await client.post(
                f"{agent_server_base_url}/internal/client-actions",
                headers=headers,
                json={
                    "conversation_id": self.payload["conversation_id"],
                    "run_id": self.run_id,
                    "agent_id": self.agent_id,
                    "action_name": action_name,
                    "args": args,
                    "timeout_ms": timeout_ms,
                },
            )
            response.raise_for_status()
            return response.json()

    async def run_model(self, prompt: str) -> OutputT:
        if not should_execute_model(self.app.state.settings):
            return self.business.fallback_factory(self)
        try:
            result = await self.agent.run(prompt, output_type=self.business.output_type)
            output = _agent_output(result)
            if isinstance(output, self.business.output_type):
                return output
            if isinstance(output, dict):
                return self.business.output_type(**output)
            return self.business.output_type.model_validate(output)
        except Exception:
            if not model_fallback_allowed(self.app.state.settings):
                raise
            return self.business.fallback_factory(self)

    def result(
        self,
        *,
        summary: str,
        items: list[str],
        ui_title: str,
        ui_props: dict[str, object],
        delivery: str = "passthrough",
    ) -> BusinessResultEnvelope:
        return BusinessResultEnvelope(
            status="completed",
            agent_id=self.agent_id,
            run_id=self.run_id,
            task_id=self.task_id,
            result_type=self.business.result_type,
            result={
                "summary": summary,
                "items": items,
                "bridge_result": self.bridge_result,
                "attachments": self.attachments,
            },
            ui=UiDescriptor(
                component=self.business.ui_component,
                component_version="v1",
                props=ui_props,
                fallback=UiFallback(component="common.markdown", props={"content": summary}),
            ),
            delivery=DeliveryDirective(mode=delivery, final=True, needs_master_summary=False),
        )

    def cancelled_event(self) -> dict[str, object]:
        return self.error_event("TASK_CANCELLED", "Task was cancelled.", recoverable=True, retryable=True, cancelled=True)

    def error_event(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool,
        retryable: bool,
        cancelled: bool = False,
    ) -> dict[str, object]:
        return {
            "type": "business.error",
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "error": to_dict(
                AgentError(
                    code=code,
                    message=message,
                    recoverable=recoverable,
                    retryable=retryable,
                    cancelled=cancelled,
                )
            ),
        }


def _agent_output(result: Any) -> Any:
    for attr in ("output", "data"):
        if hasattr(result, attr):
            return getattr(result, attr)
    return result
