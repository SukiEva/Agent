# Real MVP Design

This document defines the remaining work required to turn the current communication skeleton into a real MVP.

## Current Problem

The current implementation proves the transport path:

```text
Vue -> Agent Server -> Agent Gateway -> master_agent -> business_agent -> Agent Server SSE -> Vue
```

The first skeleton implementation did not prove a real agent runtime because it created PydanticAI agents without calling them, used deterministic demo results, and exercised Redis mostly through store tests.

The real MVP is complete only when a task can use a model-backed master route, a model-backed business result, Redis-backed runtime state, and the existing SSE UI path.

## Current Implementation Status

- `master_agent` now calls PydanticAI for routing when model execution is enabled.
- `master_agent` falls back to deterministic token scoring when the model is disabled, fails, or returns an invalid target.
- `demo_business_agent` now calls PydanticAI for `DemoBusinessResult` when model execution is enabled.
- `demo_business_agent` wraps model output in the existing `BusinessResultEnvelope` and `demo.result_card` UI descriptor.
- `demo_business_agent` registers `call_frontend_bridge` as a PydanticAI tool and reuses Agent Server's internal client-action API.
- Business agents can use `agent_core.business_app.BusinessAgentApp` to reuse the FastAPI/A2A/Redis/bridge service shell while keeping PydanticAI tool decorators on the exposed `business.pydantic` agent.
- Local memory-backed smoke passes without model credentials by using deterministic fallback behavior.
- Redis-backed end-to-end smoke remains the external verification gate when Redis is available.

## Non-Negotiable Boundaries

- Agent Server remains the only browser-facing backend.
- Agent Gateway remains thin and only routes A2A traffic.
- `master_agent` is the only agent that selects business agents.
- Business agents do not call other agents in the MVP.
- Redis is the runtime coordination layer for multi-instance behavior.
- Long-term history, durable artifacts, and audit storage remain out of scope.
- UI output remains component name plus props, not HTML or frontend patches.
- Frontend bridge tools are per-agent capabilities, not shared global tools.

## Real MVP Requirements

### R1. Model-Backed Master Routing

When `selected_agent_id` is absent, `master_agent` must call PydanticAI to choose the target business agent.

Input to the model:

- User message.
- Attachment metadata.
- Public business agents returned by Agent Gateway.
- Each agent's id, display metadata, capabilities, and health.

Output schema:

```python
class RouteDecision(BaseModel):
    target_agent_id: str
    confidence: float
    reason: str
```

Rules:

- The selected `target_agent_id` must be one of the healthy public business agents.
- Invalid model output falls back to deterministic token scoring.
- Manual `selected_agent_id` bypasses model routing.
- Routing reason is internal in the MVP and is not exposed to Vue unless debug logging is enabled.

Minimum implementation shape:

```text
_choose_business_agent()
  -> if selected_agent_id: return selected_agent_id
  -> agents = GET gateway /agents
  -> decision = await pydantic_agent.run(prompt, output_type=RouteDecision)
  -> validate decision.target_agent_id in candidates
  -> return decision.target_agent_id
```

### R2. Model-Backed Business Result

At least one business agent must call PydanticAI to generate a structured result envelope.

Input to the model:

- `BusinessTaskRequest`.
- User message.
- Attachment metadata.
- Optional frontend bridge result.
- The business agent's domain prompt.

Output schema:

```python
class DemoBusinessResult(BaseModel):
    summary: str
    items: list[str]
    ui_title: str
```

The agent then wraps that output in the existing `BusinessResultEnvelope`:

- `result_type = "demo_result.v1"`
- `result.summary` from model output.
- `result.items` from model output.
- `ui.component = "demo.result_card"`
- `ui.props` derived from model output.
- `delivery` chosen by the business agent.

Fallback:

- If model execution fails, return a structured `business.error` when the failure prevents useful work.
- For development mode, a config flag may allow deterministic fallback result generation.

### R3. PydanticAI Frontend Bridge Tool

Bridge-capable agents should expose frontend bridge calls as ordinary PydanticAI tools.

The tool implementation calls Agent Server's internal client-action API:

```text
agent tool
  -> POST /internal/client-actions
  -> Agent Server writes Redis action state and emits AG-UI tool events
  -> Vue executes bridge function
  -> POST /api/client-actions/{action_id}/result
  -> Redis action result stream unblocks the tool call
```

Tool function contract:

```python
async def call_frontend_bridge(
    action_name: str,
    args: dict[str, object],
    timeout_ms: int = 30000,
) -> dict[str, object]:
    ...
```

Rules:

- The tool is registered only inside agents that need bridge access.
- The action result is returned to the model as tool output.
- The Agent Server still only emits AG-UI tool call events; the model does not talk to the browser directly.
- Auth uses the existing internal auth extension point.

### R4. Redis-Backed Runtime Smoke

The real MVP must run with:

```text
AGENT_RUNTIME_STORE=redis
AGENT_REDIS_URL=redis://...
```

The Redis-backed smoke must prove:

- Conversation state is written and read through Redis.
- SSE replay reads from Redis streams.
- Run state is written and updated through Redis.
- Frontend bridge pending action waits on Redis blocking read.
- Cancellation command is published through Redis command streams.

The default developer command can remain memory-backed, but the MVP verification command must include Redis:

```bash
python scripts/verify_mvp.py --redis required
```

### R5. Model Configuration

Each model-backed service reads OpenAI-compatible config from service config:

```yaml
llm:
  base_url: ${oc.env:OPENAI_BASE_URL,https://api.openai.com/v1}
  api_key: ${oc.env:OPENAI_API_KEY,""}
  model: ${oc.env:OPENAI_MODEL,gpt-4.1-mini}
  temperature: ${oc.env:OPENAI_TEMPERATURE,0.2}
  timeout_seconds: ${oc.env:OPENAI_TIMEOUT_SECONDS,60}
```

Rules:

- Missing API key should fail fast only when model execution is required.
- Tests should not require a real external model.
- Unit tests use fake PydanticAI-compatible runners or dependency injection.
- One optional manual smoke can use a real OpenAI-compatible endpoint.

## Runtime Flow After Real MVP

```text
Vue POST /api/runs
  -> Agent Server creates Redis run state
  -> Agent Server calls Gateway /a2a/master_agent/tasks
  -> master_agent fetches Gateway /agents
  -> master_agent calls model for RouteDecision
  -> master_agent calls Gateway /a2a/{business_agent}/tasks
  -> business_agent optionally calls frontend bridge tool
  -> business_agent calls model for DemoBusinessResult
  -> business_agent emits business.result
  -> master_agent converts result to AG-UI text/custom UI
  -> Agent Server writes AG-UI events to Redis stream
  -> Vue receives SSE events
```

## Acceptance Gates

The real MVP is not done until all gates pass.

### Automated Gates

- Unit test: master model routing selects a valid agent from model output. Implemented in `tests/test_master_agent_routing.py`.
- Unit test: invalid master model routing falls back to deterministic routing. Implemented in `tests/test_master_agent_routing.py`.
- Unit test: business model output is wrapped into `BusinessResultEnvelope`. Implemented in `tests/test_demo_business_agent_model.py`.
- Unit test: business model failure returns a structured error or configured fallback. Implemented in `tests/test_demo_business_agent_model.py`.
- Unit test: frontend bridge tool calls Agent Server internal API and returns result. Implemented in `tests/test_demo_business_agent_model.py`.
- Redis store tests continue to cover direct Redis command usage. Implemented in `tests/test_redis_stores.py`.
- `python scripts/verify_all.py` passes locally.
- `python scripts/verify_mvp.py --redis required` passes in an environment with Redis.

### Manual Gate

With a real OpenAI-compatible endpoint configured:

1. Start Redis.
2. Start all backend services with `AGENT_RUNTIME_STORE=redis`.
3. Start Vue.
4. Submit a task without manual agent selection.
5. Confirm the master model chooses a business agent.
6. Confirm the business agent model generates the final result.
7. Confirm SSE text and `demo.result_card` UI render in the browser.
8. Confirm cancel still works during a delayed task.

## Explicitly Deferred

- Long-term chat history.
- User-visible conversation picker.
- Durable report storage.
- Multi-agent business workflows.
- Gateway policy enforcement for forbidden agent-to-agent calls.
- Redis owner-instance routing.
- Redis consumer groups.
- Complex UI patch protocol.
- Shared global tool allowlist.
- Full production observability stack.

## Implementation Order

1. Introduce injectable model runner wrappers for `master_agent` and business agents.
2. Add `RouteDecision` schema and master routing model call.
3. Add `DemoBusinessResult` schema and business model call.
4. Register frontend bridge as a PydanticAI tool in the demo business agent.
5. Extend smoke tests to assert model-backed paths with fake runners.
6. Run Redis-backed MVP verification.
7. Run optional real-model manual smoke.
