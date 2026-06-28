from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import json
from time import monotonic
from typing import Any

from agent_core.events import SseEvent
from agent_core.redis import (
    action_result_key,
    action_state_key,
    agent_command_stream_key,
    conversation_events_key,
    conversation_state_key,
    run_state_key,
)
from agent_core.schemas.bridge import ClientActionRequest, ClientActionResult
from agent_core.serialization import to_dict


@dataclass
class Conversation:
    conversation_id: str
    client_id: str
    created_at: float = field(default_factory=monotonic)


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    async def create(self, conversation_id: str, client_id: str) -> Conversation:
        conversation = Conversation(conversation_id=conversation_id, client_id=client_id)
        self._conversations[conversation_id] = conversation
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)


class InMemoryEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[SseEvent]] = defaultdict(list)
        self._conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
        self._counters: dict[str, int] = defaultdict(int)

    async def append(self, conversation_id: str, payload: dict[str, object]) -> SseEvent:
        self._counters[conversation_id] += 1
        event = SseEvent(id=str(self._counters[conversation_id]), data=payload)
        condition = self._conditions[conversation_id]
        async with condition:
            self._events[conversation_id].append(event)
            condition.notify_all()
        return event

    async def replay(self, conversation_id: str, after_event_id: str | None) -> list[SseEvent]:
        events = self._events.get(conversation_id, [])
        if not after_event_id:
            return list(events)
        try:
            after = int(after_event_id)
        except ValueError:
            return list(events)
        return [event for event in events if int(event.id) > after]

    async def stream(
        self,
        conversation_id: str,
        after_event_id: str | None = None,
        heartbeat_seconds: float = 15.0,
    ) -> AsyncIterator[SseEvent]:
        last_seen = int(after_event_id or "0")
        for event in await self.replay(conversation_id, after_event_id):
            last_seen = int(event.id)
            yield event

        condition = self._conditions[conversation_id]
        while True:
            async with condition:
                try:
                    await asyncio.wait_for(condition.wait(), timeout=heartbeat_seconds)
                except TimeoutError:
                    yield SseEvent(id=str(last_seen), event="heartbeat", data={"type": "HEARTBEAT"})
                    continue
                events = [event for event in self._events[conversation_id] if int(event.id) > last_seen]
            for event in events:
                last_seen = int(event.id)
                yield event


class InMemoryClientActionStore:
    def __init__(self) -> None:
        self._requests: dict[str, ClientActionRequest] = {}
        self._results: dict[str, ClientActionResult] = {}
        self._conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def create(self, request: ClientActionRequest) -> None:
        self._requests[request.action_id] = request

    async def complete(self, result: ClientActionResult) -> ClientActionResult:
        condition = self._conditions[result.action_id]
        async with condition:
            existing = self._results.get(result.action_id)
            if existing:
                return existing
            self._results[result.action_id] = result
            condition.notify_all()
            return result

    async def wait(self, action_id: str, timeout_ms: int) -> ClientActionResult:
        existing = self._results.get(action_id)
        if existing:
            return existing
        condition = self._conditions[action_id]
        async with condition:
            await asyncio.wait_for(condition.wait(), timeout=timeout_ms / 1000)
        return self._results[action_id]


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, dict[str, object]] = {}

    async def create(self, run_id: str, state: dict[str, object]) -> None:
        self._runs[run_id] = state

    async def update(self, run_id: str, **fields: object) -> None:
        self._runs.setdefault(run_id, {}).update(fields)

    async def get(self, run_id: str) -> dict[str, object] | None:
        return self._runs.get(run_id)


class InMemoryCommandStore:
    def __init__(self) -> None:
        self._commands: dict[str, list[dict[str, object]]] = defaultdict(list)
        self._conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def publish(self, agent_id: str, command: dict[str, object]) -> None:
        condition = self._conditions[agent_id]
        async with condition:
            self._commands[agent_id].append(command)
            condition.notify_all()

    async def stream(self, agent_id: str, heartbeat_seconds: float = 15.0) -> AsyncIterator[dict[str, object]]:
        index = 0
        condition = self._conditions[agent_id]
        while True:
            async with condition:
                while len(self._commands[agent_id]) <= index:
                    try:
                        await asyncio.wait_for(condition.wait(), timeout=heartbeat_seconds)
                    except TimeoutError:
                        continue
                pending = self._commands[agent_id][index:]
                index = len(self._commands[agent_id])
            for command in pending:
                yield command


class RedisConversationStore:
    def __init__(self, redis: Any, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def create(self, conversation_id: str, client_id: str) -> Conversation:
        conversation = Conversation(conversation_id=conversation_id, client_id=client_id)
        key = conversation_state_key(conversation_id)
        await self._redis.hset(
            key,
            mapping={
                "conversation_id": conversation_id,
                "client_id": client_id,
                "created_at": str(conversation.created_at),
            },
        )
        await self._redis.expire(key, self._ttl_seconds)
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        data = await self._redis.hgetall(conversation_state_key(conversation_id))
        if not data:
            return None
        return Conversation(
            conversation_id=str(data["conversation_id"]),
            client_id=str(data["client_id"]),
            created_at=float(data.get("created_at", "0") or 0),
        )


class RedisEventStore:
    def __init__(self, redis: Any, ttl_seconds: int, maxlen: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._maxlen = maxlen

    async def append(self, conversation_id: str, payload: dict[str, object]) -> SseEvent:
        key = conversation_events_key(conversation_id)
        event_id = await self._redis.xadd(
            key,
            {"data": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            maxlen=self._maxlen,
            approximate=True,
        )
        await self._redis.expire(key, self._ttl_seconds)
        return SseEvent(id=str(event_id), data=payload)

    async def replay(self, conversation_id: str, after_event_id: str | None) -> list[SseEvent]:
        key = conversation_events_key(conversation_id)
        min_id = f"({after_event_id}" if after_event_id else "-"
        rows = await self._redis.xrange(key, min=min_id, max="+")
        return [self._row_to_event(row) for row in rows]

    async def stream(
        self,
        conversation_id: str,
        after_event_id: str | None = None,
        heartbeat_seconds: float = 15.0,
    ) -> AsyncIterator[SseEvent]:
        last_seen = after_event_id or "0-0"
        for event in await self.replay(conversation_id, after_event_id):
            last_seen = event.id
            yield event

        key = conversation_events_key(conversation_id)
        while True:
            rows = await self._redis.xread({key: last_seen}, count=10, block=int(heartbeat_seconds * 1000))
            if not rows:
                yield SseEvent(id=last_seen, event="heartbeat", data={"type": "HEARTBEAT"})
                continue
            for _, stream_rows in rows:
                for row in stream_rows:
                    event = self._row_to_event(row)
                    last_seen = event.id
                    yield event

    def _row_to_event(self, row: tuple[str, dict[str, str]]) -> SseEvent:
        event_id, fields = row
        return SseEvent(id=str(event_id), data=json.loads(fields["data"]))


class RedisClientActionStore:
    def __init__(self, redis: Any, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def create(self, request: ClientActionRequest) -> None:
        key = action_state_key(request.action_id)
        await self._redis.hset(
            key,
            mapping={
                "status": "pending",
                "request": json.dumps(to_dict(request), ensure_ascii=False, separators=(",", ":")),
            },
        )
        await self._redis.expire(key, self._ttl_seconds)

    async def complete(self, result: ClientActionResult) -> ClientActionResult:
        state_key = action_state_key(result.action_id)
        result_key = action_result_key(result.action_id)
        existing = await self._read_existing_result(result_key)
        if existing:
            return existing
        payload = json.dumps(to_dict(result), ensure_ascii=False, separators=(",", ":"))
        await self._redis.hset(state_key, mapping={"status": result.status, "result": payload})
        await self._redis.xadd(result_key, {"data": payload}, maxlen=1, approximate=False)
        await self._redis.expire(state_key, self._ttl_seconds)
        await self._redis.expire(result_key, self._ttl_seconds)
        return result

    async def wait(self, action_id: str, timeout_ms: int) -> ClientActionResult:
        result_key = action_result_key(action_id)
        existing = await self._read_existing_result(result_key)
        if existing:
            return existing
        rows = await self._redis.xread({result_key: "0-0"}, count=1, block=timeout_ms)
        if not rows:
            raise TimeoutError(f"client action timed out: {action_id}")
        _, stream_rows = rows[0]
        _, fields = stream_rows[0]
        return ClientActionResult(**json.loads(fields["data"]))

    async def _read_existing_result(self, result_key: str) -> ClientActionResult | None:
        rows = await self._redis.xrange(result_key, min="-", max="+", count=1)
        if not rows:
            return None
        _, fields = rows[0]
        return ClientActionResult(**json.loads(fields["data"]))


class RedisRunStore:
    def __init__(self, redis: Any, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def create(self, run_id: str, state: dict[str, object]) -> None:
        await self._write(run_id, state)

    async def update(self, run_id: str, **fields: object) -> None:
        existing = await self.get(run_id) or {}
        existing.update(fields)
        await self._write(run_id, existing)

    async def get(self, run_id: str) -> dict[str, object] | None:
        data = await self._redis.get(run_state_key(run_id))
        if not data:
            return None
        return json.loads(data)

    async def _write(self, run_id: str, state: dict[str, object]) -> None:
        await self._redis.set(
            run_state_key(run_id),
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            ex=self._ttl_seconds,
        )


class RedisCommandStore:
    def __init__(self, redis: Any, ttl_seconds: int, maxlen: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._maxlen = maxlen

    async def publish(self, agent_id: str, command: dict[str, object]) -> None:
        key = agent_command_stream_key(agent_id)
        await self._redis.xadd(
            key,
            {"data": json.dumps(command, ensure_ascii=False, separators=(",", ":"))},
            maxlen=self._maxlen,
            approximate=True,
        )
        await self._redis.expire(key, self._ttl_seconds)

    async def stream(self, agent_id: str, heartbeat_seconds: float = 15.0) -> AsyncIterator[dict[str, object]]:
        key = agent_command_stream_key(agent_id)
        last_seen = "$"
        while True:
            rows = await self._redis.xread({key: last_seen}, count=10, block=int(heartbeat_seconds * 1000))
            if not rows:
                continue
            for _, stream_rows in rows:
                for event_id, fields in stream_rows:
                    last_seen = event_id
                    yield json.loads(fields["data"])


@dataclass
class RuntimeStores:
    conversations: Any = field(default_factory=InMemoryConversationStore)
    events: Any = field(default_factory=InMemoryEventStore)
    client_actions: Any = field(default_factory=InMemoryClientActionStore)
    runs: Any = field(default_factory=InMemoryRunStore)
    commands: Any = field(default_factory=InMemoryCommandStore)


def create_runtime_stores(settings: dict[str, Any]) -> RuntimeStores:
    runtime_settings = settings.get("runtime", {})
    store_kind = runtime_settings.get("store", "memory")
    if store_kind == "memory":
        return RuntimeStores()
    if store_kind != "redis":
        raise ValueError(f"unsupported runtime store: {store_kind}")

    import redis.asyncio as redis

    redis_settings = settings.get("redis", {})
    ttl_seconds = int(runtime_settings.get("ttl_seconds", 3600))
    event_maxlen = int(runtime_settings.get("event_maxlen", 1000))
    client = redis.Redis.from_url(str(redis_settings["url"]), decode_responses=True)
    return RuntimeStores(
        conversations=RedisConversationStore(client, ttl_seconds=ttl_seconds),
        events=RedisEventStore(client, ttl_seconds=ttl_seconds, maxlen=event_maxlen),
        client_actions=RedisClientActionStore(client, ttl_seconds=ttl_seconds),
        runs=RedisRunStore(client, ttl_seconds=ttl_seconds),
        commands=RedisCommandStore(client, ttl_seconds=ttl_seconds, maxlen=event_maxlen),
    )
