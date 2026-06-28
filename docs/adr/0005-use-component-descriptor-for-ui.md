# ADR-0005: Use Component Descriptors for Custom UI

## Status

Accepted

## Context

Business agents need to return structured UI output. The frontend is Vue 3 and should remain in control of actual components, styling, validation, and fallback rendering.

## Decision

Business agents return `ui.v1` component descriptors:

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

The descriptor is delivered to Vue through AG-UI `CUSTOM` event `ui.component.render`.

Component keys and prop schemas are maintained in a shared `agent-ui-contracts` package or directory. Vue maps component keys to registered components.

## Consequences

- Agents can request rich UI without emitting HTML.
- Vue controls component implementation.
- Unknown components can fall back gracefully.
- `master_agent` can pass through, summarize, or compose business output.

## Rejected Alternatives

- Agents return arbitrary HTML.
- Agents return Vue component import paths.
- Pure natural-language output only.
- Full generative UI protocol in the MVP.
