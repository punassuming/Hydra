# hydra-jobs

Hydra Jobs is a distributed job runner with:
- FastAPI scheduler
- Python workers
- Redis coordination plane
- Mongo persistence plane
- React/Ant UI

## Current Architecture

- Scheduler owns orchestration and persistence:
  - Dispatches jobs from `job_queue:<domain>:pending` to `job_queue:<domain>:<worker_id>`
  - Handles schedule loops (immediate/cron/interval)
  - Performs failover requeue on offline workers
  - Consumes worker run events from Redis (`run_events:<domain>`) and writes `job_runs` in Mongo
- Worker is Redis-only at runtime:
  - Registers metadata + token hash in Redis
  - Heartbeats and publishes rolling metrics (memory/process/load)
  - Executes jobs and emits run lifecycle events to Redis
  - Streams logs via Redis pub/sub + history lists
- Mongo stores durable data:
  - `domains`, `job_definitions`, `job_runs`

## Adopting Additional Control-Plane Ideas (No Architecture Change)

- Job scheduling/orchestration
  - Already supported: cron + interval schedules, inline executors (python/shell/batch/powershell), git source execution, retries/timeouts, and `depends_on` metadata for DAG relationships.
  - Incremental adoption path: use existing `depends_on` to power a UI DAG editor; enforce dependency gating in scheduler dispatch logic as a follow-up.
- Domain isolation
  - Already supported through domain-scoped tokens, Redis ACL credentials, and domain-partitioned queues/keys.
- Real-time observability
  - Already supported through SSE log streaming (`/runs/{run_id}/stream`) and worker metrics/timeline/operations endpoints.
- AI ops
  - Already supported: AI job generation and failure analysis endpoints.
  - Added: `/ai/predict_duration` estimates expected run duration from historical Mongo `job_runs` for predictive planning.

## Security Model

- Non-admin API access requires both:
  - `x-api-key` (domain token)
  - `domain` query/header
- Admin access uses `ADMIN_TOKEN`
- Worker auth is always domain-scoped:
  - `DOMAIN=<domain>`
  - `API_TOKEN` matching that domain
- Optional (recommended) Redis ACL hardening:
  - Per-domain worker Redis ACL password (`REDIS_PASSWORD`), username derived from `DOMAIN`
  - Key/channel permissions limited to that domain only

## Quick Start

Prereqs: Docker + Docker Compose

```bash
ADMIN_TOKEN=<your_admin_token> docker compose up --build
```

Services:
- UI: `http://localhost:5173`
- Scheduler API: `http://localhost:8000`
- Redis: `localhost:6379`
- Mongo: `localhost:27017`

## Start Workers (Recommended ACL Path)

1. Rotate/get domain token and worker Redis ACL creds from admin API (or Admin UI).
2. Launch workers with domain + token + ACL credentials:

```bash
API_TOKEN=<domain_token> \
DOMAIN=prod \
WORKER_REQUIRE_REDIS_ACL=true \
REDIS_URL=redis://localhost:6379/0 \
REDIS_PASSWORD=<worker_redis_acl_password> \
docker compose -f docker-compose.worker.yml up --build --scale worker=2
```

Notes:
- Worker no longer requires `MONGO_URL`/`MONGO_DB`.
- Workers communicate through Redis; scheduler persists runs into Mongo.

## Sentinel Support

Scheduler and worker support Redis Sentinel:
- `REDIS_SENTINELS=host1:26379,host2:26379`
- `REDIS_SENTINEL_MASTER=mymaster`
- optional sentinel auth:
  - `REDIS_SENTINEL_USERNAME`
  - `REDIS_SENTINEL_PASSWORD`
- redis auth:
  - `REDIS_PASSWORD`

If Sentinel vars are not set, `REDIS_URL` is used.

## Domain ACL Scripts

- Bootstrap via scheduler admin API:
  - `scripts/provision-redis-acl.sh`
- Configure external Redis directly with `redis-cli`:
  - `scripts/configure-external-redis-acl.sh`
- Agentic worker bring-up (Docker/K8s/Bare):
  - `scripts/start-domain-workers.sh <domain> [scale]`
  - Set `WORKER_BACKEND=docker|k8s|bare|print`
- Agentic domain diagnostics (API + optional Redis deep checks):
  - `scripts/diagnose-domain-admin.sh <domain>`
  - Set `REDIS_CHECK_MODE=auto|none|docker|k8s|cli`

These scripts keep worker auth aligned to `DOMAIN + API_TOKEN + REDIS_PASSWORD` and support domain-scoped ACL operations.

## Worker Status Semantics

Worker status is split into two dimensions:
- `connectivity_status`: heartbeat-derived `online|offline`
- `dispatch_status`: scheduler dispatch mode `online|draining|offline`

`POST /workers/{id}/state` accepts:
- `online`
- `draining`
- `offline`
- `disabled` (legacy alias for `offline`)

## Worker Operations Timeline

`GET /workers/{id}/operations` returns operational events such as:
- start/restart
- state changes (online/draining/offline)
- dispatches
- run start/end/result
- failover/offline events

UI Worker Detail includes an operational timeline panel.

## API Highlights

- Jobs:
  - `GET /jobs/`
  - `POST /jobs/`
  - `PUT /jobs/{job_id}`
  - `POST /jobs/{job_id}/run`
  - `POST /jobs/validate`
  - `POST /jobs/{job_id}/validate`
  - `POST /jobs/adhoc`
- Runs/Logs:
  - `GET /jobs/{job_id}/runs`
  - `GET /runs/{run_id}`
  - `GET /runs/{run_id}/stream` (SSE)
- AI:
  - `POST /ai/generate_job`
  - `POST /ai/analyze_run`
  - `POST /ai/predict_duration`
- Workers:
  - `GET /workers/`
  - `GET /workers/{id}/metrics`
  - `GET /workers/{id}/timeline`
  - `GET /workers/{id}/operations`
  - `POST /workers/{id}/state`
- Admin:
  - `GET /admin/domains`
  - `POST /admin/domains`
  - `POST /admin/domains/{domain}/token`
  - `POST /admin/domains/{domain}/redis_acl/rotate`

## UI Notes

- If unauthenticated, only login is shown.
- Header includes persistent light/dark mode toggle and direct Admin entry.
- Log viewer supports search, parsed/raw mode, expand, and copy.
- AI log helper supports:
  - failure remediation
  - summary
  - error extraction
  - retry tuning
  - custom question mode

## Redis Keys (Core)

- `job_queue:<domain>:pending`
- `job_queue:<domain>:<worker_id>`
- `workers:<domain>:<worker_id>`
- `worker_heartbeats:<domain>`
- `worker_running_set:<domain>:<worker_id>`
- `job_running:<domain>:<job_id>`
- `worker_metrics:<domain>:<worker_id>:history`
- `run_events:<domain>`
- `worker_ops:<domain>:<worker_id>`
- `log_stream:<domain>:<run_id>*`

## Troubleshooting

- `CORS` errors:
  - Set `CORS_ALLOW_ORIGINS` correctly (`comma-separated` or `*`)
  - Ensure scheduler is reachable from UI host
- Worker unauthorized/offline:
  - Verify `DOMAIN` + `API_TOKEN`
  - Verify domain token rotation did not invalidate old workers
  - If ACL required, verify `REDIS_PASSWORD`
- Storage pressure:
  - Low disk can corrupt Mongo startup; recover space before restart
  - Check `docker system df` and prune unused cache/volumes carefully

## Development

- Scheduler local:
  - `uvicorn scheduler.main:app --reload --host 0.0.0.0 --port 8000`
- UI local:
  - `cd ui && npm install && npm run dev`
  - Cypress e2e:
    - `cd ui && npm run cypress:open` (interactive)
    - `cd ui && npm run cypress:run` (headless, expects UI at `http://localhost:5173`)
- Helpful docs/scripts:
  - `doc/docker-compose-workflows.md`
  - `doc/testing.md`
  - `scripts/`
