# Agent System Architecture Overview

## Goal

Build a real-time agent application with a Vue 3 frontend, an Agent Server entrypoint, a thin A2A Agent Gateway, and independently deployable business agents implemented in Python with PydanticAI and fasta2a.

The system optimizes for real-time task execution, not long-term chat history. Redis Cluster is the core coordination layer for online sessions, short replay windows, bridge actions, cancellation, and runtime state.

## Components

### Vue Web App

- Opens a single live conversation for the current page lifecycle.
- Connects to Agent Server through SSE.
- Sends run requests and cancellation requests over HTTP.
- Executes frontend bridge tool calls and posts results back to Agent Server.
- Renders AG-UI-compatible events and custom UI component descriptors.

### Agent Server

Agent Server is the human-facing entrypoint.

It owns:

- User-facing HTTP APIs.
- SSE connection management.
- Conversation and run lifecycle.
- Short-term event replay through Redis.
- Client bridge action delivery and result collection.
- Authenticator extension points.
- Calling the configured `master_agent` through Agent Gateway.

It does not own:

- Business intent recognition.
- Business agent selection.
- Business workflow planning.
- Direct agent service discovery.

### Agent Gateway

Agent Gateway is a thin A2A infrastructure service.

It owns:

- Static agent registry loading.
- Agent Card discovery and caching.
- `/agents` directory APIs.
- A2A request routing.
- Downstream health status.
- Route-level validation, cancellation forwarding, and downstream error preservation.

It does not own:

- User sessions.
- Business intent recognition.
- Business result interpretation.
- UI rendering decisions.

### Master Agent

`master_agent` is a standard A2A agent registered in the gateway.

It owns:

- Reading available business agents from Agent Gateway.
- Intent recognition when the user did not manually select a business agent.
- Dispatching to one business agent.
- Translating business progress to user-visible AG-UI progress events.
- Handling business result envelopes.
- Deciding whether to pass through, summarize, or compose final output.

### Business Agents

Business agents are standard A2A agents built with fasta2a and PydanticAI.

They own:

- Domain prompts and tools.
- Domain-specific result schemas.
- Domain-specific UI descriptors.
- Progress events and final result envelopes.

Business agents do not call other agents in the MVP. Only `master_agent` orchestrates agent calls. This is an architectural convention in the MVP, not enforced by gateway policy yet.

## Core Decisions

- All browser traffic goes through Agent Server.
- All agent traffic goes through Agent Gateway.
- Agent Server calls only the configured `master_agent`.
- `master_agent` calls business agents through Agent Gateway.
- Gateway exposes the full agent list internally.
- Agent Server exposes only public business capabilities to Vue.
- Frontend events use an AG-UI-compatible subset.
- Business agent communication uses structured business envelopes, not raw AG-UI.
- Redis Cluster is the short-term runtime coordination layer.
- No long-term database is required in the MVP.
- UI output uses registered component keys and props, not arbitrary HTML or Vue import paths.
