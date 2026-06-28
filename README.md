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
docker compose -f deploy/docker-compose.yml up -d redis
uv run --package agent-server agent-server
uv run --package agent-gateway agent-gateway
uv run --package master-agent master-agent
uv run --package demo-business-agent demo-business-agent
```

To start the four Python services in one terminal:

```bash
python scripts/dev_services.py
```

The script waits for each service's `/health` endpoint before reporting success. To start the services, run the backend smoke test, and stop afterward:

```bash
python scripts/dev_services.py --smoke --exit-after-smoke
```

To run the same stack against Redis-backed runtime state, start Redis and pass the runtime store to all services:

```bash
docker compose -f deploy/docker-compose.yml up -d redis
python scripts/dev_services.py --runtime-store redis --smoke --exit-after-smoke
```

With the four services already running, verify the backend path:

```bash
python scripts/smoke_backend.py
```

Run the local non-network checks:

```bash
python scripts/verify_all.py
```

The local stack defaults to the in-memory runtime store. To use Redis-backed runtime state without `dev_services.py`, set `AGENT_RUNTIME_STORE=redis` for Agent Server, master agent, and business agents:

```bash
AGENT_RUNTIME_STORE=redis uv run --package agent-server agent-server
AGENT_RUNTIME_STORE=redis uv run --package master-agent master-agent
AGENT_RUNTIME_STORE=redis uv run --package demo-business-agent demo-business-agent
```

User and internal auth default to noop for local development. They can be switched through environment variables:

```bash
AGENT_USER_AUTH_MODE=header
AGENT_INTERNAL_AUTH_MODE=shared_secret
AGENT_INTERNAL_AUTH_SECRET=dev-secret
```

For browser validation with header-style user auth, set frontend identity env vars. The app sends headers on `fetch` requests and query identity on SSE because native `EventSource` cannot set custom headers:

```bash
VITE_AGENT_USER_ID=dev-user
VITE_AGENT_TENANT_ID=dev-tenant
```

Files are stored through the local FileStore by default:

```bash
AGENT_FILE_STORE_ROOT=.data/files
```

Upload files through `POST /api/files`, then pass returned `file_id` metadata in `POST /api/runs` attachments.

## Frontend

```bash
bun install
bun run web:dev
```

The frontend is a validation shell. It is expected to consume AG-UI-compatible SSE events from Agent Server.

Set `VITE_AGENT_SERVER_URL` if Agent Server is not running on `http://localhost:8000`.
