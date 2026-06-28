# ADR-0003: Use Redis Cluster for Real-Time Coordination

## Status

Accepted

## Context

Agent Server and Agent services can run multiple instances behind load balancers. SSE holders, client bridge actions, task owners, and cancellation commands require cross-instance coordination.

The product does not require long-term chat history in the MVP.

## Decision

Use Redis Cluster as the real-time coordination layer.

Redis stores:

- Short-term conversation event streams.
- Online session and connection state.
- Client action state and results.
- Run and task status.
- Task owner instance metadata.
- Per-instance command streams.

## Consequences

- Multi-instance coordination does not require sticky HTTP routing.
- Bridge actions can wait using Redis blocking reads.
- Cancellation reaches owner instances through Redis commands.
- Redis data loss recovery is out of scope for the MVP.

## Rejected Alternatives

- Database as the primary event and session store.
- In-memory process maps only.
- Direct WebSocket routing to specific backend instances.
- Pure Redis Pub/Sub without persisted short-term streams.
