# Hydra Jobs

## Project Overview

Hydra Jobs is a distributed job runner designed for flexibility and scalability. It features a FastAPI-based scheduler, cross-platform python workers, and a React-based user interface.

**Key Components:**

*   **Scheduler Service:** A Python FastAPI application that exposes a REST API for job management. It handles job submission, validation, scheduling (cron/interval), and dispatching to workers via Redis. It also supports Server-Sent Events (SSE) for real-time updates.
    *   **AI Integration:** Uses Google Gemini or OpenAI for generating job definitions from natural language and analyzing job failures.
*   **Worker Service:** A Python application that consumes jobs from Redis queues. It supports various execution environments (shell, python, batch) and handles concurrency, heartbeats, and result reporting to MongoDB.
    *   **Git Support:** Can clone and execute code directly from Git repositories.
*   **UI:** A React application built with Vite, TypeScript, and Ant Design. It provides a visual interface for monitoring jobs, workers, and run history, with integrated AI tools.
*   **Data Store:**
    *   **Redis:** Used for job queues, worker coordination, heartbeats, and pub/sub.
    *   **MongoDB:** Stores persistent data including job definitions, run history, and domain metadata.

## Architecture

*   **Language:** Python 3.11 (Backend), TypeScript (Frontend)
*   **Frameworks:** FastAPI (Scheduler), React + Vite (UI)
*   **Database:** MongoDB (v6.0 recommended, v5.0 for broader CPU support), Redis (v7-alpine)
*   **AI Provider:** Google Gemini (requires `GEMINI_API_KEY`) or OpenAI (requires `OPENAI_API_KEY`)
*   **Infrastructure:** Docker & Docker Compose

## Workflow & Architecture (Internal Details)

- Scheduler (`scheduler/`) runs three background loops: `scheduling_loop` dispatches jobs from `job_queue:<domain>:pending` to `job_queue:<domain>:<worker_id>`, `failover_loop` requeues jobs from offline workers, and `schedule_trigger_loop` advances cron/interval jobs. API auth is enforced via `ADMIN_TOKEN` or domain tokens hashed in Mongo/Redis, and non-admin requests must include both domain + token.
- Scheduler worker APIs include:
  - `GET /workers/` with runtime + 30m metrics summary (memory/process/load), running jobs, and running users.
  - `GET /workers/{worker_id}/metrics` for time-series points.
  - `GET /workers/{worker_id}/timeline` for per-worker execution spans (for Gantt/timeline UI).
  - `POST /workers/{worker_id}/state` with JSON body `{ "state": "online|draining|disabled" }`.
- Worker (`worker/`) registers itself in Redis with tags/allowed users/domain token hash, heartbeats every 2s, BLPOPs its queue, tracks `current_running`/`worker_running_set`, streams logs to Redis (per-domain channels), and writes run docs to Mongo via `record_run_start`/`record_run_end`.
- Worker heartbeat stores rolling metrics in Redis (`worker_metrics:<domain>:<worker_id>:history`) including `memory_rss_mb`, `process_count`, and Linux load averages.
- Jobs support `bypass_concurrency`; scheduler can dispatch these even when workers are at quota, and workers execute them outside normal `ThreadPoolExecutor` limits.
- Executors support Linux-only impersonation and Kerberos bootstrap: `executor.impersonate_user` and `executor.kerberos.{principal,keytab,ccache}`.
- Domains: default `prod` is seeded on scheduler startup; additional domains live in Mongo (`domains` collection) with token hashes cached in Redis. Admin token bypasses domain scoping; domain tokens scope all other requests.
- UI (`ui/`) consumes the scheduler API/SSE for jobs, workers, history, and log streaming. Docker Compose builds and serves it on port 5173; adjust `VITE_API_BASE_URL` as needed.
- UI auth/UX notes:
  - Login gate: when unauthenticated, only the auth modal/screen is shown.
  - Header has tabbed nav, persistent dark/light toggle, and a Settings drawer for domain/token/admin actions.
  - Worker detail page includes metrics trend plotting + concurrency-lane timeline/Gantt.
  - Theme and key panel states persist via localStorage.

## Project Structure & Key Modules

- `scheduler/main.py` bootstraps FastAPI + CORS and starts the scheduling/failover/schedule threads.
- `scheduler/api/*` expose jobs, workers, health, events (SSE), logs streaming, history, and admin domain/template management.
- `scheduler/api/workers.py` — worker list/state + metrics/timeline endpoints.
- `scheduler/api/ai.py` — AI endpoints (Generate/Analyze).
- `scheduler/models/*` define Pydantic models for jobs, runs, workers, executors, and scheduling.
- `scheduler/utils/*` house affinity checks, worker selection, failover logic, auth helpers, schedule math, and logging setup.
- `worker/worker.py` registers the worker, maintains heartbeats, and executes jobs concurrently via `ThreadPoolExecutor`.
- `worker/utils/*` contain shell/exec helpers, python env prep (`uv`/venv/system), completion criteria evaluation, concurrency counters, and heartbeats.
- `worker/utils/git.py` — Git clone/checkout logic.
- `worker/executor.py` — Job execution engine (shell/python/batch/external) with git source support.
- `worker/executor.py` — also handles Linux impersonation + Kerberos pre-auth when configured.
- `ui/src/App.tsx` — Main React component.
- `ui/src/api/` — API client with domain-scoped token management.
- `ui/src/components/JobForm.tsx` — Job creation form with AI generation.
- `ui/src/components/JobRuns.tsx` — Run history with AI failure analysis.
- `examples/` holds submission scripts/templates; `deploy/k8s` has manifests; `docker-compose*.yml` define local stacks.
- `tests/` — Backend integration and unit tests.
- `tests/test_ai.py` — AI endpoint tests.

## Building and Running

The project relies heavily on Docker Compose for orchestration.

### Prerequisites

*   Docker
*   Docker Compose
*   Git (for local development)

### Quick Start (Full Stack)

To start the scheduler, worker, UI, Redis, and MongoDB:

```bash
# Using the helper script (recommended for dev)
./scripts/dev-up.sh

# OR using docker-compose directly
ADMIN_TOKEN=admin_secret GEMINI_API_KEY=<your_key> OPENAI_API_KEY=<your_key> docker compose up --build
```

The services will be available at:
*   **UI:** http://localhost:5173
*   **Scheduler API:** http://localhost:8000
*   **Redis:** localhost:6379
*   **MongoDB:** localhost:27017

### Running a Worker Separately

Workers can be run independently to scale processing power.

```bash
API_TOKEN=<domain_token> WORKER_DOMAIN=prod \
REDIS_URL=redis://localhost:6379/0 MONGO_URL=mongodb://localhost:27017 \
docker compose -f docker-compose.worker.yml up --build

# Scale workers (WORKER_ID defaults to auto-generated unique IDs)
API_TOKEN=<domain_token> WORKER_DOMAIN=prod \
docker compose -f docker-compose.worker.yml up --build --scale worker=2
```

### Development Servers

For local development without Docker:

- Scheduler: `uvicorn scheduler.main:app --reload --host 0.0.0.0 --port 8000`
- UI: `npm install && npm run dev` inside `ui/` (set `VITE_API_BASE_URL`)

### Helper Scripts

Located in `scripts/`:
*   `dev-up.sh`: Starts the development stack.
*   `dev-down.sh`: Stops the development stack.
*   `test.sh`: Runs Python backend tests.
*   `test-all.sh`: Runs all tests.
*   `worker-up.sh`: Helper to start a worker.
*   `build-images.sh`: Builds Docker images.
*   `create-domain.sh`: Creates a new domain via the API.

## Testing

### Backend (Python)

*   Uses `pytest` for testing.
*   Run tests: `./scripts/test.sh` or `pytest tests/`
*   Specific tests: `pytest tests/test_scheduler.py tests/test_worker.py`
*   Test files located in `tests/`
*   Note: The end-to-end test is skipped unless the full stack is running.

### Frontend (React)

*   Uses `vitest` for testing.
*   Run tests: `cd ui && npm test`

## Configuration Notes

### Common Environment Variables

- `REDIS_URL` — Redis connection URL
- `REDIS_SENTINELS` — Comma-separated Sentinel hosts (`host1:26379,host2:26379`)
- `REDIS_SENTINEL_MASTER` — Sentinel master name (e.g. `mymaster`)
- `REDIS_DB` — Redis DB index for Sentinel mode (default `0`)
- `REDIS_SOCKET_TIMEOUT` — Redis/Sentinel socket timeout seconds (default `2`)
- `REDIS_USERNAME` / `REDIS_PASSWORD` — Redis auth for master connection
- `REDIS_SENTINEL_USERNAME` / `REDIS_SENTINEL_PASSWORD` — Optional Sentinel auth
- `MONGO_URL` — MongoDB connection URL
- `MONGO_DB` — MongoDB database name
- `SCHEDULER_HEARTBEAT_TTL` — Heartbeat TTL for workers
- `CORS_ALLOW_ORIGINS` — CORS allowed origins
- `ADMIN_TOKEN` — Admin authentication token
- `ADMIN_DOMAIN` — Admin domain name
- `GEMINI_API_KEY` — Google Gemini API key for AI features
- `OPENAI_API_KEY` — OpenAI API key for AI features
- `LOG_LEVEL` — Logging level

### Worker Environment Variables

- `WORKER_DOMAIN` — Domain the worker belongs to
- `WORKER_DOMAIN_TOKEN` (or `API_TOKEN`) — Authentication token for the worker
- `WORKER_ID` — Unique worker identifier
- `WORKER_TAGS` — Tags for worker affinity
- `ALLOWED_USERS` — Users allowed to submit jobs to this worker
- `MAX_CONCURRENCY` — Maximum concurrent jobs
- `WORKER_STATE` — Initial worker state
- `DEPLOYMENT_TYPE` — Type of deployment
- `WORKER_METRICS_SAMPLE_SECONDS` — sampling interval for worker metrics history (default `15`)
- `WORKER_METRICS_WINDOW_SECONDS` — rolling metrics retention window in seconds (default `1800`)

### Additional Notes

- Docker images target Python 3.11 slim; `uv` is optional but must be present in the image to use the `uv` python environment.
- Environment variables can be configured via `.env` file (see `.env.example`).
- MongoDB uses a named volume `mongo-data` for persistence.
- Redis connection precedence: if both `REDIS_SENTINELS` and `REDIS_SENTINEL_MASTER` are set, scheduler/worker use Sentinel discovery; otherwise they use `REDIS_URL`.

## AI Features

*   **Magic Job Generator:** In the UI "New Job" form, use natural language to generate job JSON. Select between Gemini and OpenAI from the dropdown.
*   **Failure Analysis:** In the Run Logs view, click "Analyze Failure" to get AI-driven remediation steps. Select between Gemini and OpenAI.
*   **Configuration:** Ensure `GEMINI_API_KEY` and/or `OPENAI_API_KEY` are set in the Scheduler environment.

## Git Source Execution

Jobs can now specify a git repository as a source.

```json
{
  "source": {
    "url": "https://github.com/user/repo.git",
    "ref": "main",
    "path": "scripts"
  },
  "executor": { "type": "shell", "script": "./run.sh" }
}
```

The worker will clone the repo to a temporary directory, switch to `path` (if provided), and execute the script within that context.

## Development Conventions

### Backend (Python)

*   **Location:** `scheduler/` and `worker/`
*   **Style:** Adheres to standard Python 3.11 practices. Type hints are encouraged.
*   **Formatting:** Linting/formatting are not configured; match existing style (4-space indent, type hints where present).

### Frontend (React)

*   **Location:** `ui/`
*   **Stack:** React, TypeScript, Vite, Ant Design.
*   **Linting:** Standard Vite/React configurations.

## Known Gaps / Cleanup Targets

- Queue-based routing is not implemented; all dispatching is per worker/domain. If queues are needed, add scheduler-side selection rules and worker registration metadata accordingly.

## Working Agreements

- Commit after each meaningful change with a clear description of what changed and why. Keep commits small and scoped.
- Use `git status`/`git diff` frequently before committing to keep the working tree clean and to avoid drifting config or lockfiles.
- When editing, align affinity/capability expectations across scheduler, worker, and UI to prevent drift between enforcement and presentation.
- Keep `AGENTS.md` current whenever architecture, APIs, auth behavior, deployment workflow, or operator-facing features change.
