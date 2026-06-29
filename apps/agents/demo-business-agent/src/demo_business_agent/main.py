from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from agent_core.business_app import BusinessAgentApp, BusinessTaskContext
from agent_core.schemas.business import BusinessResultEnvelope
from agent_core.server import hypercorn_bind


class DemoBusinessResult(BaseModel):
    summary: str
    items: list[str] = Field(default_factory=list)
    ui_title: str = "Demo Result"


def _conf_dir() -> Path:
    return Path(__file__).resolve().parent / "conf"


def _fallback_business_result(ctx: BusinessTaskContext[DemoBusinessResult]) -> DemoBusinessResult:
    return DemoBusinessResult(
        summary=f"Processed: {ctx.user_message_text}",
        items=["A2A routing worked", "SSE replay path is ready", "UI descriptor delivered"],
        ui_title="Demo Result",
    )


business = BusinessAgentApp(
    title="Demo Business Agent",
    conf_dir=_conf_dir(),
    result_type="demo_result.v1",
    ui_component="demo.result_card",
    output_type=DemoBusinessResult,
    system_prompt="Run the demo business task and return structured business results.",
    fallback_factory=_fallback_business_result,
)


@business.task
async def run_demo(ctx: BusinessTaskContext[DemoBusinessResult]) -> BusinessResultEnvelope:
    bridge_result = await ctx.maybe_frontend_bridge()
    result = await ctx.run_model(_business_result_prompt(ctx, bridge_result))
    return ctx.result(
        summary=result.summary,
        items=result.items,
        ui_title=result.ui_title,
        ui_props={
            "title": result.ui_title,
            "summary": result.summary,
            "items": result.items,
            "attachments": ctx.attachments,
        },
        delivery="passthrough",
    )


def _business_result_prompt(
    ctx: BusinessTaskContext[DemoBusinessResult],
    bridge_result: dict[str, object] | None,
) -> str:
    request = {
        "user_message": ctx.user_message_text,
        "attachments": ctx.attachments,
        "bridge_result": bridge_result,
    }
    return (
        "Generate a concise demo business result for the user. "
        "Return only the structured DemoBusinessResult fields requested by the output schema. "
        "Use call_frontend_bridge only if you need live browser context beyond the provided bridge_result.\n\n"
        f"{json.dumps(request, ensure_ascii=False, separators=(',', ':'))}"
    )


app = business.create_app()


def create_app():
    return business.create_app()


async def call_frontend_bridge(
    action_name: str,
    args: dict[str, object],
    timeout_ms: int = 30000,
) -> dict[str, object]:
    return await business.call_frontend_bridge(action_name, args, timeout_ms)


def main() -> None:
    import asyncio
    import hypercorn.asyncio
    import hypercorn.config

    config = hypercorn.config.Config()
    config.bind = hypercorn_bind(app.state.settings)
    asyncio.run(hypercorn.asyncio.serve(app, config))
