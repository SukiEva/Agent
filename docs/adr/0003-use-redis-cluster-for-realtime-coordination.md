# ADR-0003: Use Redis Cluster for Real-Time Coordination

## Status

Accepted

## Context

Agent Server and Agent services can run multiple instances behind load balancers. SSE holders, client bridge actions, running task state, and cancellation commands require cross-instance coordination.

The product does not require long-term chat history in the MVP.

## Decision

Use Redis Cluster as the real-time coordination layer.

Redis stores:

- Short-term conversation event streams.
- Online session and connection state.
- Client action state and results.
- Run and task status.
- Per-agent command streams for cancellation.

## Consequences

- Multi-instance coordination does not require sticky HTTP routing.
- Bridge actions can wait using Redis blocking reads.
- Cancellation is broadcast through per-agent Redis command streams; only the instance holding the local task acts on a matching task ID.
- Redis data loss recovery is out of scope for the MVP.

## Rejected Alternatives

- Database as the primary event and session store.
- In-memory process maps only.
- Direct WebSocket routing to specific backend instances.
- Pure Redis Pub/Sub without persisted short-term streams.
