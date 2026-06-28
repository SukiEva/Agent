# ADR-0004: Use Master Agent for Routing and Orchestration

## Status

Accepted

## Context

Initial design placed intent recognition in Agent Server. That would make Agent Server understand business routing and risk duplicating logic with the orchestration layer.

## Decision

Agent Server does not perform intent recognition. It always creates the root A2A task for configured `master_agent`.

`master_agent`:

- Reads available business agents from Agent Gateway.
- Respects manual `selected_agent_id`.
- Performs intent routing when no manual selection exists.
- Calls exactly one business agent in the MVP.
- Converts business events to user-visible AG-UI events.

## Consequences

- Agent Server remains an entrypoint and session service.
- Business routing evolves inside agent logic.
- Manual frontend selection and automatic routing use the same path.
- Business agents do not call other agents in the MVP.

## Rejected Alternatives

- Agent Server performs intent recognition.
- Agent Server directly calls selected business agents.
- Every business agent can call every other business agent.
- Gateway performs business routing.
