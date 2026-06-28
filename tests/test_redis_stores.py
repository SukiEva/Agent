from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from agent_core.events import agui_run_started, agui_text_delta
from agent_core.schemas.bridge import ClientActionRequest, ClientActionResult
from agent_core.stores import (
    RedisClientActionStore,
    RedisCommandStore,
    RedisConversationStore,
    RedisEventStore,
    RedisRunStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self.strings: dict[str, str] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
        self.expires: dict[str, int] = {}
        self._sequence = 0
        self._condition = asyncio.Condition()

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes[key].update(mapping)

    async def expire(self, key: str, ttl: int) -> None:
        self.expires[key] = ttl

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def xadd(
        self,
        key: str,
        fields: dict[str, str],
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        del approximate
        async with self._condition:
            self._sequence += 1
            event_id = f"{self._sequence}-0"
            self.streams[key].append((event_id, dict(fields)))
            if maxlen is not None:
                self.streams[key] = self.streams[key][-maxlen:]
            self._condition.notify_all()
            return event_id

    async def xrange(
        self,
        key: str,
        min: str = "-",
        max: str = "+",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        del max
        rows = self._rows_after(key, min)
        if count is not None:
            return rows[:count]
        return rows

    async def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        normalized = {
            key: self._latest_id(key) if last_seen == "$" else last_seen for key, last_seen in streams.items()
        }
        deadline = None if block is None else asyncio.get_running_loop().time() + (block / 1000)
        async with self._condition:
            while True:
                result = self._read_available(normalized, count)
                if result or block is None:
                    return result
                remaining = deadline - asyncio.get_running_loop().time() if deadline is not None else None
                if remaining is not None and remaining <= 0:
                    return []
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    return []

    async def get(self, key: str) -> str | None:
        return self.strings.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.strings[key] = value
        self.expires[key] = ex

    def _read_available(
        self,
        streams: dict[str, str],
        count: int | None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        result = []
        for key, last_seen in streams.items():
            rows = self._rows_after(key, f"({last_seen}")
            if count is not None:
                rows = rows[:count]
            if rows:
                result.append((key, rows))
        return result

    def _rows_after(self, key: str, min_id: str) -> list[tuple[str, dict[str, str]]]:
        if min_id == "-":
            return list(self.streams.get(key, []))
        exclusive = min_id.startswith("(")
        lower_bound = min_id[1:] if exclusive else min_id
        return [
            row
            for row in self.streams.get(key, [])
            if self._compare_ids(row[0], lower_bound) > (0 if exclusive else -1)
        ]

    def _latest_id(self, key: str) -> str:
        rows = self.streams.get(key, [])
        return rows[-1][0] if rows else "0-0"

    def _compare_ids(self, left: str, right: str) -> int:
        left_ms, left_seq = (int(part) for part in left.split("-", 1))
        right_ms, right_seq = (int(part) for part in right.split("-", 1))
        return (left_ms > right_ms) - (left_ms < right_ms) or (left_seq > right_seq) - (left_seq < right_seq)


def test_redis_runtime_stores_use_expected_commands() -> None:
    asyncio.run(_redis_runtime_stores_use_expected_commands())


async def _redis_runtime_stores_use_expected_commands() -> None:
    redis = FakeRedis()
    conversations = RedisConversationStore(redis, ttl_seconds=60)
    events = RedisEventStore(redis, ttl_seconds=60, maxlen=100)
    actions = RedisClientActionStore(redis, ttl_seconds=60)
    runs = RedisRunStore(redis, ttl_seconds=60)
    commands = RedisCommandStore(redis, ttl_seconds=60, maxlen=100)

    conversation = await conversations.create("conv_1", "client_1")
    assert await conversations.get("conv_1") == conversation
    assert "conversation:{conv_1}:state" in redis.expires

    first = await events.append("conv_1", agui_run_started("run_1"))
    second = await events.append("conv_1", agui_text_delta("msg_1", "hello"))
    assert [event.id for event in await events.replay("conv_1", None)] == [first.id, second.id]
    assert [event.id for event in await events.replay("conv_1", first.id)] == [second.id]

    action = ClientActionRequest(
        action_id="act_1",
        conversation_id="conv_1",
        run_id="run_1",
        agent_id="demo_business_agent",
        action_name="get_selected_text",
    )
    await actions.create(action)
    result = ClientActionResult(action_id="act_1", status="completed", result={"text": "hello"})
    assert await actions.complete(result) == result
    late_result = ClientActionResult(action_id="act_1", status="completed", result={"text": "late"})
    assert await actions.complete(late_result) == result
    assert await actions.wait("act_1", 100) == result

    await runs.create("run_1", {"status": "queued"})
    await runs.update("run_1", status="running", task_id="task_1")
    assert await runs.get("run_1") == {"status": "running", "task_id": "task_1"}

    command_stream = commands.stream("demo_business_agent", heartbeat_seconds=0.1)
    next_command: asyncio.Task[dict[str, Any]] = asyncio.create_task(anext(command_stream))
    await asyncio.sleep(0)
    await commands.publish("demo_business_agent", {"type": "cancel_task", "task_id": "task_1"})
    assert await asyncio.wait_for(next_command, timeout=1) == {"type": "cancel_task", "task_id": "task_1"}
    await command_stream.aclose()


if __name__ == "__main__":
    test_redis_runtime_stores_use_expected_commands()
    print("redis store tests ok")
