# Hydra Jobs — Architecture

## Component Overview

| Component | Role |
|---|---|
| **Scheduler** | FastAPI service: REST API, job orchestration, scheduling, failover, and persistence |
| **Redis** | Message bus: job queues, worker coordination, heartbeats, log streaming, run events |
| **MongoDB** | Durable store: domains, job definitions, run history, credentials |
| **Workers** | Execution agents: Redis-only at runtime — receive jobs, run them, emit events. Available in Python and Go with feature parity. |
| **UI** | React frontend: monitors jobs/workers/runs via scheduler REST API and SSE |

## Architecture Diagram

```mermaid
flowchart TB
    UI["React UI\n(Vite + Ant Design)"]

    subgraph Scheduler["Scheduler (FastAPI)"]
        API["REST API\n+ SSE streams"]
        STL["Schedule Trigger Loop\n(cron / interval → dispatch)"]
        DFL["Dispatch / Failover Loop\n(pending queue → worker queues)"]
        REL["Run Event Loop\n(run_events → MongoDB)"]
    end

    subgraph Stores["Data Stores"]
        Redis[("Redis\n· job queues\n· heartbeats\n· log streams\n· run events\n· worker ops")]
        MongoDB[("MongoDB\n· domains\n· job_definitions\n· job_runs\n· credentials")]
    end

    subgraph WorkerPool["Workers (per domain, Redis-only)"]
        WA1["Worker\n(domain-a)"]
        WA2["Worker\n(domain-a)"]
        WB1["Worker\n(domain-b)"]
    end

    %% UI ↔ Scheduler
    UI -- "HTTP / SSE" --> API
    API -- "read / write" --> MongoDB

    %% Scheduler internal loops ↔ Redis + MongoDB
    STL -- "advance schedule" --> MongoDB
    STL -- "enqueue pending" --> Redis
    DFL -- "read worker state\n+ pending queue" --> Redis
    DFL -- "dispatch → worker queue" --> Redis
    REL -- "consume run_events" --> Redis
    REL -- "persist job_runs" --> MongoDB

    %% Scheduler resolves credentials at dispatch time
    DFL -- "resolve credential_refs" --> MongoDB

    %% Redis → Workers (job dispatch)
    Redis -- "BLPOP job dispatch" --> WA1
    Redis -- "BLPOP job dispatch" --> WA2
    Redis -- "BLPOP job dispatch" --> WB1

    %% Workers → Redis (heartbeat / logs / events)
    WA1 -- "heartbeat · logs\nrun events · ops" --> Redis
    WA2 -- "heartbeat · logs\nrun events · ops" --> Redis
    WB1 -- "heartbeat · logs\nrun events · ops" --> Redis
```

## Data Flow

### Job Submission & Dispatch
1. Client submits a job via `POST /jobs/` → scheduler validates and stores in **MongoDB**.
2. **Schedule Trigger Loop** fires when a cron/interval expression is due and enqueues a run into `job_queue:<domain>:pending` in **Redis**.
3. **Dispatch Loop** picks the best worker using affinity rules, resolves credential refs from **MongoDB**, and pushes the full job envelope to `job_queue:<domain>:<worker_id>` in **Redis**.
4. **Worker** BLPOPs its dedicated queue, executes the job, and streams logs to `log_stream:<domain>:<run_id>` in **Redis**.

### Run Lifecycle Events
5. Worker emits `run_start` and `run_end` events to `run_events:<domain>` in **Redis**.
6. **Run Event Loop** (in scheduler) consumes those events and persists run documents to the `job_runs` collection in **MongoDB**.

### Worker Coordination (Redis-only)
- Workers write registration metadata and heartbeats to `workers:<domain>:<worker_id>` in **Redis**.
- Rolling metrics (memory, CPU, load) are stored in `worker_metrics:<domain>:<worker_id>:history` in **Redis**.
- Operational events (dispatches, state changes, failovers) are logged to `worker_ops:<domain>:<worker_id>` in **Redis**.
- Workers **never connect to MongoDB**.

## Redis Key Layout

| Key Pattern | Owner | Purpose |
|---|---|---|
| `job_queue:<domain>:pending` | Scheduler (write) / Scheduler (read) | Pending jobs waiting for dispatch |
| `job_queue:<domain>:<worker_id>` | Scheduler (write) / Worker (read) | Per-worker dispatch queue |
| `workers:<domain>:<worker_id>` | Worker | Registration metadata + heartbeat |
| `worker_heartbeats:<domain>` | Worker | Heartbeat timestamps |
| `worker_running_set:<domain>:<worker_id>` | Worker | Set of currently running job IDs |
| `job_running:<domain>:<job_id>` | Worker | Concurrency lock per job |
| `worker_metrics:<domain>:<worker_id>:history` | Worker | Rolling metrics history |
| `run_events:<domain>` | Worker (write) / Scheduler (read) | Run lifecycle event stream |
| `worker_ops:<domain>:<worker_id>` | Worker | Operational event log |
| `log_stream:<domain>:<run_id>*` | Worker | Real-time log chunks |

## Security Boundaries

- Each domain has its own **Redis ACL user** (username = domain name). Workers can only access keys and channels scoped to their domain.
- The scheduler's admin token grants cross-domain access; domain tokens scope all other requests.
- **Credentials** (DB URIs, PAT tokens, SMTP passwords) are encrypted in MongoDB and resolved at dispatch time by the scheduler. Workers receive them in the job envelope — they are never returned via the API.

## Executor Types

Both Python and Go workers support the following executor types:

| Type | Description | Notes |
|---|---|---|
| `shell` | Run a shell script (bash/sh) | Default executor |
| `external` | Run an external binary | Direct command execution |
| `python` | Run inline Python code | Python worker has venv/uv support |
| `powershell` | Run PowerShell scripts | Requires pwsh or powershell |
| `batch` | Run Windows batch scripts | Windows only |
| `sql` | Execute SQL queries | Supports postgres, mysql, mssql, oracle, mongodb; uses credential_ref for secrets |
| `http` | Make HTTP requests | REST triggers, webhooks, health checks; supports credential_ref for auth |
| `sensor` | Poll until a condition is met | HTTP or SQL sensor; runs on worker, not scheduler |

### Sensor Executor

Sensor jobs (`executor.type == "sensor"`) are dispatched and executed entirely on workers — the scheduler does **not** perform any external polling. This preserves the architectural boundary that the scheduler orchestrates and persists while workers execute.

A sensor worker thread polls a target at `poll_interval_seconds` intervals until either:
- The condition is met (HTTP: expected status received; SQL: query returns ≥1 row) → `run_end` status `success`
- `timeout_seconds` elapses → `run_end` status `failed`

Credentials (`credential_ref`) for sensor jobs are resolved by the scheduler at dispatch time and injected into the job envelope, exactly as for other executor types. Workers have no MongoDB access.

### Worker Capability Detection

Workers advertise only executor types that pass a concrete preflight check at startup:

| Capability | Preflight check |
|---|---|
| `shell` / `external` | At least one shell binary executes `exit 0` successfully |
| `python` | `HYDRA_PYTHON_PATH` or `python3`/`python` found and executable |
| `powershell` | `pwsh` or `powershell` executes `exit 0` successfully |
| `batch` | Windows OS detected |
| `sql` | Python present **and** `sqlalchemy` or `pymongo` importable |
| `http` | Always available (stdlib `urllib`) |
| `sensor` | Always available (HTTP sensor uses stdlib; SQL sensor requires same as `sql`) |

This fail-closed approach prevents dispatch of jobs to workers that lack the necessary runtime, rather than discovering the gap at execution time.

### Cross-Platform User Control

- **Impersonation**: Jobs can specify `executor.impersonate_user` to run commands as a different user via `sudo -n -u <user>` (Linux/macOS). The scheduler enforces OS affinity — impersonation jobs only dispatch to Linux/macOS workers.
- **Kerberos**: Jobs can specify `executor.kerberos` with `principal`, `keytab`, and optional `ccache` for Kerberos authentication bootstrap before execution.
- **Windows**: Use the service account model — run workers as the target user and use `allowed_users` affinity for routing.

### Workspace Caching

Workers maintain a persistent cache directory for source workspaces. Cache entries are keyed by `(url, ref, path, protocol)` hash and support:
- **LRU eviction** with configurable max size (`WORKER_WORKSPACE_CACHE_MAX_MB`)
- **Configurable TTL metadata** (`WORKER_WORKSPACE_CACHE_TTL`) based on the last recorded cache-use timestamp
- **Git fast-update** (fetch + checkout instead of full clone on cache hit)
- **Cache modes** per job: `auto` (default), `always`, `never`

## Startup and Cold-Start Timing

Hydra instruments key stages of job execution so operators can observe where time is spent. The following timing fields are included in `run_end` events (and therefore persisted to MongoDB `job_runs`):

| Field | Description |
|---|---|
| `queue_latency_ms` | Time from job enqueue to worker thread start (dispatch latency) |
| `total_run_ms` | Wall-clock time from `run_start` to `run_end` |
| `source_fetch_ms` | Time spent fetching/updating the workspace (git clone, copy, rsync). `null` if no source is configured. |
| `env_prep_ms` | Time to prepare the Python execution environment (venv create, uv install). `null` for non-Python executors. |

Additionally, each worker records `startup_duration_ms` in its registration metadata (`workers:<domain>:<worker_id>`) and in the `start`/`restart` worker operation event. This measures the time from process start to first successful registration, capturing the cost of capability detection, dependency checks, and Redis connection setup.

### Querying timing data

Timing fields are available on `GET /history/` run records. To identify cold-start bottlenecks:

```bash
# Summarise source_fetch_ms for a specific job (using mongosh or any MongoDB client)
db.job_runs.aggregate([
  { $match: { job_id: "my-job-id" } },
  { $group: { _id: null, avg_fetch: { $avg: "$source_fetch_ms" }, p95_total: { $percentile: { input: "$total_run_ms", p: [0.95], method: "approximate" } } } }
])
```
