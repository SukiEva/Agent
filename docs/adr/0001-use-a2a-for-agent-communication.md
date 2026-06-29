# ADR-0001: Use A2A for Agent Communication

## Status

Accepted

## Context

The system has multiple independently deployable agents. Agents need a common task protocol, Agent Card discovery, streaming events, and cancellation.

## Decision

Use A2A for Agent Server to `master_agent` and `master_agent` to business agent communication. Agent services are built with fasta2a and expose Agent Cards. Agent Gateway routes task traffic without parsing business payloads.

## Consequences

- Agent services share one protocol surface.
- Agent Gateway stays thin and infrastructure-focused.
- `master_agent` is also a normal A2A agent.
- Business payloads remain outside gateway responsibility.

## Rejected Alternatives

- Direct Agent Server to business agent calls.
- Agent mesh where any business agent can call any other business agent.
- MCP for agent-to-agent communication.
- Custom HTTP endpoints per business agent.
