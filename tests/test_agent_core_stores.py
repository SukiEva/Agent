from __future__ import annotations

import asyncio

from agent_core.events import agui_run_started
from agent_core.redis import (
    action_result_key,
    action_state_key,
    agent_command_stream_key,
    conversation_events_key,
    conversation_state_key,
    run_state_key,
)
from agent_core.schemas.bridge import ClientActionRequest, ClientActionResult
from agent_core.stores import create_runtime_stores


def test_redis_keys_use_hash_tags() -> None:
    assert conversation_state_key("conv_1") == "conversation:{conv_1}:state"
    assert conversation_events_key("conv_1") == "conversation:{conv_1}:events"
    assert action_state_key("act_1") == "action:{act_1}:state"
    assert action_result_key("act_1") == "action:{act_1}:result"
    assert run_state_key("run_1") == "run:{run_1}:state"
    assert agent_command_stream_key("demo_business_agent") == "agent:{demo_business_agent}:commands"


def test_memory_runtime_store_roundtrip() -> None:
    asyncio.run(_memory_runtime_store_roundtrip())


async def _memory_runtime_store_roundtrip() -> None:
    stores = create_runtime_stores({"runtime": {"store": "memory"}})
    conversation = await stores.conversations.create("conv_1", "client_1")
    assert conversation.conversation_id == "conv_1"
    assert await stores.conversations.get("conv_1") == conversation

    await stores.events.append("conv_1", agui_run_started("run_1"))
    replayed = await stores.events.replay("conv_1", None)
    assert replayed[0].data["type"] == "RUN_STARTED"

    await stores.runs.create("run_1", {"status": "queued"})
    await stores.runs.update("run_1", status="running")
    assert await stores.runs.get("run_1") == {"status": "running"}

    action = ClientActionRequest(
        action_id="act_1",
        conversation_id="conv_1",
        run_id="run_1",
        agent_id="demo_business_agent",
        action_name="get_selected_text",
    )
    await stores.client_actions.create(action)
    result = ClientActionResult(action_id="act_1", status="completed", result={"text": "hello"})
    await stores.client_actions.complete(result)
    assert await stores.client_actions.wait("act_1", 100) == result

    await stores.commands.publish("demo_business_agent", {"type": "cancel_task", "task_id": "task_1"})
    commands = stores.commands.stream("demo_business_agent")
    command = await asyncio.wait_for(anext(commands), timeout=1)
    assert command == {"type": "cancel_task", "task_id": "task_1"}
    await commands.aclose()


if __name__ == "__main__":
    test_redis_keys_use_hash_tags()
    test_memory_runtime_store_roundtrip()
    print("agent core store tests ok")
