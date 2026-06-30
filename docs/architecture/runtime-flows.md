# Runtime Flows

## Startup

1. Agent services start and expose fasta2a A2A endpoints and Agent Cards.
2. Agent Gateway loads its static registry from local configuration.
3. Agent Gateway fetches Agent Cards and caches business metadata.
4. Agent Server starts with a configured `master_agent_id`.
5. Vue starts and creates a new conversation through Agent Server.

## Capability Listing

```text
Vue
  -> Agent Server GET /api/capabilities
  -> Agent Gateway GET /agents
  <- full agent list
  <- public business capabilities only
```

Gateway returns all known agents, including `master_agent`. Agent Server filters out internal or non-business agents before returning capabilities to Vue.

## Run Execution

```text
Vue
  -> Agent Server POST /api/runs
  -> Agent Gateway POST /a2a/{master_agent_id}/tasks
  -> master_agent
  -> Agent Gateway POST /a2a/{business_agent_id}/tasks
  -> business_agent
```

The run request uses a structured envelope with:

- `conversation_id`
- `client_id`
- user message
- optional `selected_agent_id`
- attachments
- frontend context

Agent Server does not perform intent recognition. It passes manual selection and context to `master_agent`.

## Business Progress

```text
business_agent
  -> A2A stream business.progress
  -> master_agent
  -> AG-UI CUSTOM business.progress
  -> Agent Gateway
  -> Agent Server
  -> Redis conversation event stream
  -> Vue SSE
```

Business agents stream internal progress envelopes. `master_agent` decides whether to forward them as AG-UI custom progress events.
The frontend renders these events as a folded analysis timeline. These events are user-visible status updates, not raw model chain-of-thought.

## Final Result

```text
business_agent
  -> business.result envelope
  -> master_agent
  -> AG-UI text and/or CUSTOM ui.component.render
  -> Agent Server
  -> Redis
  -> Vue
```

Business result envelopes include:

- `status`
- `result_type`
- `result`
- `ui`
- `delivery`
- `error`, when failed

`delivery.mode` controls whether `master_agent` should pass through, summarize, or compose the final user output.
The final user output is emitted as AG-UI text start/content/end events. Long text may be split across multiple content deltas and assembled by Vue.

## Frontend Bridge Tool

```text
business or bridge-capable agent tool
  -> Agent Server internal client action API
  -> Redis pending action and request stream
  -> Agent Server instance holding SSE connection
  -> AG-UI TOOL_CALL_* events over SSE
  -> Vue bridge runtime
  -> Agent Server POST /api/client-actions/{action_id}/result
  -> Redis action result stream
  -> waiting tool call resumes
```

The tool appears synchronous to the PydanticAI agent, but the transport is asynchronous through Redis.

## Cancellation

```text
Vue
  -> Agent Server POST /api/runs/{run_id}/cancel
  -> Agent Gateway cancel master task
  -> master_agent cancels active business task
  -> Agent Gateway cancel business task
  -> Redis per-agent command stream
  -> instance holding the local task calls asyncio.Task.cancel()
```

When requests land on arbitrary instances behind an ALB, cancellation is not routed by HTTP to a specific instance. Every live instance of the target agent listens to the per-agent command stream; only the instance that owns the local task for the task ID cancels anything.

## SSE Reconnect

SSE is opened per conversation:

```http
GET /api/conversations/{conversation_id}/events
Last-Event-ID: <event_id>
```

Agent Server replays events from the Redis conversation stream within the configured retention window, then resumes blocking reads for new events.

Page refresh creates a new conversation in the MVP. Replay is only for short network interruptions in the same page lifecycle.
