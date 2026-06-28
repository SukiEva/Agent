from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from time import monotonic

from agent_core.events import SseEvent
from agent_core.schemas.bridge import ClientActionRequest, ClientActionResult


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


@dataclass
class RuntimeStores:
    conversations: InMemoryConversationStore = field(default_factory=InMemoryConversationStore)
    events: InMemoryEventStore = field(default_factory=InMemoryEventStore)
    client_actions: InMemoryClientActionStore = field(default_factory=InMemoryClientActionStore)
    runs: InMemoryRunStore = field(default_factory=InMemoryRunStore)
