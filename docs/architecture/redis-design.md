# Redis Design

## Role

Redis Cluster is the real-time coordination layer. It is not the long-term system of record.

Redis stores:

- Online conversation and client connection state.
- Short-term AG-UI-compatible conversation event streams.
- Pending frontend bridge actions and results.
- Run and task short-term status.
- Agent task owner instance metadata.
- Per-instance command streams for cancellation.
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

task:{task_1}:state
task:{task_1}:commands

agent_instance:{inst_1}:heartbeat
agent_commands:{inst_1}:stream
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

Each running A2A task records its owner instance:

```text
task:{task_id}:state
```

Cancel requests may land on any instance. The receiver writes:

```text
cancel_requested = true
```

and appends a cancel command to the owner instance command stream:

```text
agent_commands:{owner_instance_id}:stream
```

The owner instance listens to its command stream and calls `asyncio.Task.cancel()` on the local task.

Long-running tasks should also check the `cancel_requested` flag at cooperative checkpoints.

## Persistence Boundary

The MVP assumes Redis Cluster is available. It does not define recovery semantics for Redis data loss. If Redis state is lost, in-flight runs may fail and users may retry.
