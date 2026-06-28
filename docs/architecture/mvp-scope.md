# MVP Scope

## Included

- Vue 3 validation frontend.
- Agent Server with HTTP APIs and SSE.
- Agent Gateway with static registry and `/agents`.
- `master_agent` as a standard A2A agent.
- `demo_business_agent` as a fake business agent.
- Redis Cluster-compatible stores.
- Short-term SSE replay.
- Frontend bridge action round trip.
- Cancellation through Redis command streams.
- Component descriptor rendering.
- Config loading through OmegaConf and typed settings.
- JSON structured logging through a shared SDK.
- OpenAI-compatible model configuration.

## Excluded

- Long-term chat history.
- Database-backed audit trail.
- Multi-tab conversation semantics.
- Page refresh conversation recovery.
- Dynamic agent registration.
- Gateway-enforced caller policy.
- Running task migration after owner instance death.
- Complex UI patch streaming.
- Full AG-UI client surface area.
- MCP tools.
- Multiple LLM provider abstractions beyond OpenAI-compatible endpoints.

## Demo Paths

The first implementation should validate four paths:

1. Normal task execution with progress, final text, and UI component render.
2. Manual business agent selection through capabilities.
3. Frontend bridge tool call and result return.
4. User cancellation propagating through Agent Server, Gateway, and agents.

## Reliability Boundary

The MVP is a real-time task system. It supports short replay windows for transient SSE disconnections, but it does not promise long-term session recovery.

If Redis state is lost or the owner agent instance dies, in-flight tasks may fail and users may retry.
