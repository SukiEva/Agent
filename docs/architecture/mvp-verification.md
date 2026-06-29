# MVP Verification Matrix

This document maps the MVP scope to concrete verification evidence.

## Verified Locally

| Requirement | Evidence |
| --- | --- |
| Vue 3 validation frontend | `bun run web:typecheck`, `bun run web:build`, frontend runtime event tests in `scripts/verify_all.py` |
| Agent Server HTTP APIs and SSE | `scripts/dev_services.py --smoke --exit-after-smoke`, `tests/test_agent_server_auth.py`, `tests/test_agent_server_files.py` |
| Agent Gateway static registry and `/agents` | `tests/test_agent_gateway.py`, backend smoke `capabilities ok` |
| `master_agent` as routable A2A agent | backend smoke routes all runs through `/a2a/master_agent/tasks` |
| `demo_business_agent` as fake business agent | backend smoke normal, bridge, attachment, and cancel cases |
| Agent Card generation with fasta2a schema | `tests/test_a2a_cards.py` |
| Manual business agent selection | backend smoke `normal` case sends `selected_agent_id` |
| Automatic master routing | backend smoke `auto-route` case omits `selected_agent_id`; `tests/test_master_agent_routing.py` |
| Short-term SSE replay | backend smoke `replay` case validates `Last-Event-ID` behavior |
| Frontend bridge action round trip | backend smoke `bridge` case validates AG-UI tool events and result POST |
| Cancellation propagation | backend smoke `cancel` case validates Agent Server to Gateway to agents cancellation path |
| Component descriptor rendering | backend smoke `normal` and `attachment` cases validate `ui.component.render`; `tests/test_ui_contracts.py` |
| Attachments with bare `file_id` | backend smoke `attachment` case; `tests/test_files.py` |
| Config loading through OmegaConf and typed settings | `tests/test_config.py` |
| JSON structured logging SDK | `tests/test_logging.py` |
| OpenAI-compatible PydanticAI model config | `tests/test_llm.py` |
| User auth and internal auth extension points | `tests/test_auth.py`, `tests/test_agent_server_auth.py` |
| Redis Cluster-compatible key layout and store command semantics | `tests/test_agent_core_stores.py`, `tests/test_redis_stores.py` |
| Redis runtime preflight | `tests/test_dev_services.py`; `scripts/dev_services.py --runtime-store redis` fails fast when Redis is unreachable |

## Primary Commands

```bash
python scripts/verify_all.py
python scripts/dev_services.py --smoke --exit-after-smoke
```

## CI Verification

`.github/workflows/mvp.yml` runs the same verification suite in GitHub Actions, including a Redis service-backed smoke:

- `python scripts/verify_all.py`
- `python scripts/dev_services.py --smoke --exit-after-smoke`
- `python scripts/dev_services.py --runtime-store redis --smoke --exit-after-smoke`

For Redis-backed runtime state:

```bash
docker compose -f deploy/docker-compose.yml up -d redis
python scripts/dev_services.py --runtime-store redis --smoke --exit-after-smoke
```

## Current External Gap

The local environment used for this verification did not provide Docker, `redis-server`, or `redis-cli`, so the Redis-backed end-to-end smoke could not be executed here.

The repository includes:

- Redis store implementations using `redis.asyncio`.
- Redis Cluster-compatible hash-tag key helpers.
- Fake Redis store tests covering `hset`, `hgetall`, `xadd`, `xrange`, `xread`, `get`, `set`, and `expire` usage.
- `deploy/docker-compose.yml` for local Redis.
- `dev_services.py` Redis preflight with clear failure output.

The remaining local confirmation step is running the Redis-backed smoke command in an environment with Redis available. CI is configured to provide Redis as a service and run that command automatically.
