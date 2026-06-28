# Redis Design

## Role

Redis Cluster is the real-time coordination layer. It is not the long-term system of record.

Redis stores:

- Online conversation and client connection state.
- Short-term AG-UI-compatible conversation event streams.
- Pending frontend bridge actions and results.
- Run and task short-term status.
- Short-term running task metadata.
- Per-agent command streams for cancellation.
- Gateway health cache, optionally.

Redis does not store:

- Long-term chat history.
- Audit records.
- Reports.
- Large file contents.
- Permanent artifacts.

## Cluster Key Design

Keys should be designed for Redis Cluster from the first version. Related keys that require multi-key operations should use hash tags.

Examples:

```text
conversation:{conv_1}:state
conversation:{conv_1}:events

run:{run_1}:state

action:{act_1}:state
action:{act_1}:result

agent:{demo_business_agent}:commands
```

Cross-slot transactions should be avoided. When two resources are related but do not require atomic multi-key operations, store the related ID in the value.

## Event Streams

Conversation events store user-visible AG-UI-compatible events only.

Internal A2A events are not copied wholesale into the conversation stream. Internal task state lives in dedicated run/task keys.

Conversation event streams should have:

- Maximum length.
- TTL.
- Monotonic event IDs for SSE replay.

## Client Actions

Client bridge actions use:

```text
action:{action_id}:state
action:{action_id}:result
```

The waiting tool call blocks on the result stream with Redis blocking read. Frontend result POST writes to the result stream and updates state.

Action state should include:

- `conversation_id`
- `run_id`
- `agent_id`
- `action_name`
- `status`
- `timeout_ms`
- `created_at`

Owner agent instance migration is not supported in the MVP. If the waiting agent instance dies, the action times out or expires.

## Cancellation

The MVP uses per-agent command broadcast instead of owner-instance addressing:

```text
agent:{agent_id}:commands
```

Cancel requests may land on any instance behind an ALB. The receiver appends a cancel command to the target agent's command stream. Every live instance of that agent listens to the same stream; only the instance holding the local `asyncio.Task` for the task ID cancels anything.

Long-running tasks should also check the `cancel_requested` flag at cooperative checkpoints.

This avoids endpoint-specific routing and extra owner heartbeat state in the MVP. A future version can replace broadcast with owner-instance streams or Redis consumer groups if command volume or duplicate delivery becomes a problem.

## Persistence Boundary

The MVP assumes Redis Cluster is available. It does not define recovery semantics for Redis data loss. If Redis state is lost, in-flight runs may fail and users may retry.
