# Protocol Boundaries

## Vue to Agent Server

Frontend communication uses HTTP plus SSE.

Primary APIs:

```http
POST /api/conversations
GET /api/conversations/{conversation_id}/events
GET /api/capabilities
POST /api/runs
POST /api/runs/{run_id}/cancel
POST /api/client-actions/{action_id}/result
POST /api/files
```

SSE events are AG-UI-compatible. The MVP supports an AG-UI subset:

- Run lifecycle events.
- Text message events.
- Tool call events for frontend bridge actions.
- Custom events for user-visible analysis progress and UI rendering.

## Agent Server to Agent Gateway

Agent Server calls Agent Gateway for:

- Capability listing.
- Creating the root task for `master_agent`.
- Cancellation.

Agent Server does not know individual business agent addresses.

## Agent Gateway to Agents

Agent Gateway routes the MVP A2A task traffic to fasta2a-based agent services.

Gateway validates route targets, discovers Agent Cards, forwards task streams, forwards cancellation requests, and preserves downstream error status. It does not parse business payloads.

## Master Agent to Business Agents

`master_agent` calls business agents through Agent Gateway using A2A.

Business task input uses a shared `BusinessTaskRequest` envelope. Business task output uses:

- `business.progress`
- `business.result`
- `business.error`

Business agents do not directly emit AG-UI events as their public result protocol.
`business.progress` is public execution or analysis progress for the user interface, not raw model chain-of-thought.

## PydanticAI and AG-UI

PydanticAI's AG-UI adapter can be used inside agent services where it fits agent runtime event conversion.

Agent Server still owns Redis-backed SSE delivery and replay. It should not expose PydanticAI `dispatch_request()` directly to the browser because that would bypass:

- Agent Gateway.
- Redis event replay.
- Multi-instance SSE coordination.
- Client bridge action routing.
- System-wide cancellation.

## Frontend Bridge

Frontend bridge calls are modeled as agent tools, but their execution happens in the current Vue client.

SSE downlink uses AG-UI tool call events. The result uplink uses:

```http
POST /api/client-actions/{action_id}/result
```

Complete bridge results are not written to the conversation event stream by default. The conversation stream records only completion or failure status unless an action explicitly allows result persistence.

## UI Rendering

Custom UI output uses AG-UI `CUSTOM` events named:

```text
ui.component.render
```

Payload uses `ui.v1` component descriptor:

```json
{
  "schema_version": "ui.v1",
  "component": "contract.review_report",
  "component_version": "v1",
  "props": {},
  "fallback": {
    "component": "common.markdown",
    "props": {
      "content": "..."
    }
  }
}
```

Component names are registry keys, not Vue import paths or HTML.
