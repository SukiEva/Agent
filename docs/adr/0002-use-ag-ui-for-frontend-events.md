# ADR-0002: Use AG-UI-Compatible Frontend Events

## Status

Accepted

## Context

Vue needs to receive live run lifecycle, text, progress, bridge tool, and UI render events. The event protocol should be compatible with existing agent UI tooling without forcing the frontend into a React-specific component stack.

## Decision

Use an AG-UI-compatible event subset over SSE between Agent Server and Vue.

Use:

- AG-UI run and text events for assistant output.
- AG-UI tool call events for frontend bridge actions.
- AG-UI custom events for business progress and UI component rendering.

Vue may use AG-UI TypeScript SDK types and client utilities, but renders its own UI.

## Consequences

- The frontend protocol is not invented from scratch.
- PydanticAI AG-UI integration can be used inside agent services.
- Agent Server still owns Redis-backed SSE delivery and replay.
- Custom UI rendering remains controlled by Vue component registry.

## Rejected Alternatives

- Raw custom SSE event format only.
- Full CopilotKit React frontend stack.
- Direct PydanticAI `dispatch_request()` from browser to agent service.
- WebSocket-only frontend protocol.
