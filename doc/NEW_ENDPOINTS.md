# New API Endpoints Documentation

This document describes the new API endpoints added to support comprehensive frontend capabilities.

## Job Management Endpoints

### DELETE /jobs/{job_id}
Delete a job definition. Removes the job from the database and clears any pending queue entries.

**Request:**
- Path parameter: `job_id` (string)
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "ok": true,
  "job_id": "abc123"
}
```

**Notes:**
- Historical runs are preserved
- Only removes the job definition and pending queue entries
- Requires domain access or admin token

---

### POST /jobs/{job_id}/pause
Pause a scheduled job by disabling its schedule.

**Request:**
- Path parameter: `job_id` (string)
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "ok": true,
  "job_id": "abc123",
  "status": "paused"
}
```

**Notes:**
- Only works for scheduled jobs (interval/cron)
- Cannot pause immediate jobs
- Does not affect already queued or running instances

---

### POST /jobs/{job_id}/resume
Resume a paused scheduled job by re-enabling its schedule.

**Request:**
- Path parameter: `job_id` (string)
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "ok": true,
  "job_id": "abc123",
  "status": "resumed"
}
```

---

### PATCH /jobs/{job_id}
Partially update a job definition (alias to PUT endpoint).

**Request:**
- Path parameter: `job_id` (string)
- Headers: `x-api-key` (required)
- Body: Partial JobUpdate object

**Response:**
- Returns updated JobDefinition

**Example:**
```json
{
  "priority": 8,
  "timeout": 300
}
```

---

### POST /jobs/bulk
Create multiple jobs in a single request.

**Request:**
- Headers: `x-api-key` (required)
- Body: Array of JobCreate objects (max 100)

**Response:**
```json
[
  { "id": "job1", "name": "test-1", ... },
  { "id": "job2", "name": "test-2", ... }
]
```

**Notes:**
- Maximum 100 jobs per request
- Partial failures stop processing and return error with index
- All jobs inherit the domain from the API token

---

## Worker Management Endpoints

### GET /workers/{worker_id}
Get details for a specific worker.

**Request:**
- Path parameter: `worker_id` (string)
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "worker_id": "worker-01",
  "domain": "prod",
  "os": "linux",
  "tags": ["gpu", "large"],
  "max_concurrency": 4,
  "current_running": 2,
  "running_jobs": ["job1", "job2"],
  ...
}
```

**Notes:**
- Returns 404 if worker not found
- Admin tokens can search across all domains

---

## Run Management Endpoints

### GET /runs/
List all runs with optional filtering and pagination.

**Request:**
- Query parameters:
  - `job_id` (optional): Filter by job ID
  - `status` (optional): Filter by status (success, failed, running)
  - `limit` (optional): Number of results (default 100, max 1000)
  - `skip` (optional): Pagination offset (default 0)
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "runs": [...],
  "total": 150,
  "limit": 100,
  "skip": 0
}
```

---

### DELETE /runs/{run_id}
Delete a specific run from history.

**Request:**
- Path parameter: `run_id` (string)
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "ok": true,
  "run_id": "run123"
}
```

**Notes:**
- Useful for cleaning up test runs or removing sensitive data
- Requires domain access or admin token

---

## Statistics Endpoints

### GET /stats/overview
Get system-wide statistics including jobs, runs, workers, and queue metrics.

**Request:**
- Headers: `x-api-key` (required)

**Response:**
```json
{
  "domains": [
    {
      "domain": "prod",
      "jobs_count": 50,
      "runs_count": 1000,
      "success_count": 950,
      "failed_count": 50,
      "running_count": 2,
      "workers_count": 5,
      "pending_count": 3,
      "active_jobs": 2
    }
  ],
  "total_jobs": 50,
  "total_runs": 1000,
  "total_workers": 5,
  "total_pending": 3,
  "total_running": 2
}
```

**Notes:**
- Admin tokens see all domains
- Regular tokens only see their own domain
- Provides comprehensive system health overview

---

## Model Changes

### JobDefinition and JobCreate
Added `user` field (string, default: "default") to track job ownership.

**Example:**
```json
{
  "name": "my-job",
  "user": "alice",
  "affinity": {...},
  "executor": {...}
}
```

---

## HTTP Methods Support

All job endpoints now support RESTful HTTP methods:
- GET: Retrieve resources
- POST: Create new resources
- PUT: Replace existing resources
- PATCH: Partially update resources
- DELETE: Remove resources

---

## Error Responses

All endpoints return standard HTTP error codes:
- `400`: Bad request (invalid parameters)
- `403`: Forbidden (insufficient permissions)
- `404`: Not found
- `422`: Validation error
- `500`: Internal server error

Error response format:
```json
{
  "detail": "Error message here"
}
```
