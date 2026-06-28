# Agent Runtime

This repository is a scaffold for a real-time agent system with:

- Vue 3 validation frontend.
- Agent Server for user-facing HTTP and SSE.
- Agent Gateway for thin A2A routing.
- fasta2a-based master and business agents.
- Shared Python SDK in `agent-core`.
- Redis Cluster as the runtime coordination layer.

Architecture decisions live in `docs/architecture` and `docs/adr`.

## Python Workspace

Python packages are managed with `uv workspace`.

```bash
uv sync
uv run --package agent-server agent-server
uv run --package agent-gateway agent-gateway
uv run --package master-agent master-agent
uv run --package demo-business-agent demo-business-agent
```

With the four services running, verify the backend path:

```bash
python scripts/smoke_backend.py
```

## Frontend

```bash
bun install
bun run web:dev
```

The frontend is a validation shell. It is expected to consume AG-UI-compatible SSE events from Agent Server.

Set `VITE_AGENT_SERVER_URL` if Agent Server is not running on `http://localhost:8000`.
