# Hydra Jobs API - Complete Endpoint Reference

This document provides a comprehensive list of all available API endpoints organized by functional area.

## Table of Contents
- [Job Management](#job-management)
- [Worker Management](#worker-management)
- [Run Management](#run-management)
- [Statistics](#statistics)
- [Admin & Domains](#admin--domains)
- [AI Assistance](#ai-assistance)
- [Events & Monitoring](#events--monitoring)
- [Health](#health)

---

## Job Management

### List Jobs
```
GET /jobs/
```
Returns all jobs visible to the authenticated user.

### Get Job Details
```
GET /jobs/{job_id}
```
Returns detailed information about a specific job.

### Create Job
```
POST /jobs/
```
Creates a new job definition.

### Update Job (Full)
```
PUT /jobs/{job_id}
```
Replaces a job definition with new values.

### Update Job (Partial)
```
PATCH /jobs/{job_id}
```
Updates only specified fields of a job definition.

### Delete Job
```
DELETE /jobs/{job_id}
```
Deletes a job definition (preserves historical runs).

### Validate Job
```
POST /jobs/validate
POST /jobs/{job_id}/validate
```
Validates a job definition without creating it.

### Run Job Manually
```
POST /jobs/{job_id}/run
```
Enqueues a job for immediate execution.

### Pause Scheduled Job
```
POST /jobs/{job_id}/pause
```
Disables scheduling for a job (does not affect running instances).

### Resume Scheduled Job
```
POST /jobs/{job_id}/resume
```
Re-enables scheduling for a paused job.

### Create Ad-hoc Job
```
POST /jobs/adhoc
```
Creates and immediately runs a one-time job.

### Bulk Create Jobs
```
POST /jobs/bulk
```
Creates multiple jobs in a single request (max 100).

### Job Overview
```
GET /overview/jobs
```
Returns aggregated statistics for all jobs with recent run data.

### Job Grid View
```
GET /jobs/{job_id}/grid
```
Returns grid view data for visualizing job runs.

### Job Gantt View
```
GET /jobs/{job_id}/gantt
```
Returns Gantt chart data for job run timeline.

### Job Graph View
```
GET /jobs/{job_id}/graph
```
Returns graph structure for job dependencies (future use).

---

## Worker Management

### List Workers
```
GET /workers/
```
Returns all workers visible to the authenticated user.

### Get Worker Details
```
GET /workers/{worker_id}
```
Returns detailed information about a specific worker.

### Set Worker State
```
POST /workers/{worker_id}/state
```
Sets worker state to: `online`, `draining`, or `disabled`.

**Body:**
```json
{
  "state": "draining"
}
```

---

## Run Management

### List Runs
```
GET /runs/?job_id={job_id}&status={status}&limit={limit}&skip={skip}
```
Returns runs with optional filtering and pagination.

**Query Parameters:**
- `job_id` (optional): Filter by job ID
- `status` (optional): Filter by status (success, failed, running)
- `limit` (optional): Max results per request (default 100, max 1000)
- `skip` (optional): Pagination offset (default 0)

### Get Run Details
```
GET /runs/{run_id}
```
Returns detailed information about a specific run.

### Stream Run Logs
```
GET /runs/{run_id}/stream
```
Server-Sent Events (SSE) stream of live run logs.

### Delete Run
```
DELETE /runs/{run_id}
```
Deletes a run from history (useful for cleanup).

### Get Job Runs
```
GET /jobs/{job_id}/runs
```
Returns all runs for a specific job.

---

## Statistics

### System Overview
```
GET /stats/overview
```
Returns comprehensive system statistics across all domains.

**Response includes:**
- Per-domain stats (jobs, runs, workers, queues)
- System-wide aggregates
- Success/failure counts
- Active job counts

---

## Admin & Domains

### List Domains
```
GET /admin/domains
```
Returns all domains (admin only).

### Create Domain
```
POST /admin/domains
```
Creates a new domain (admin only).

### Update Domain
```
PUT /admin/domains/{domain}
```
Updates domain metadata (admin only).

### Rotate Domain Token
```
POST /admin/domains/{domain}/token
```
Generates a new token for a domain (admin only).

### Delete Domain
```
DELETE /admin/domains/{domain}
```
Deletes a domain (admin only).

### List Job Templates
```
GET /admin/job_templates
```
Returns available job templates (admin only).

### Import Template
```
POST /admin/job_templates/{template_id}/import
```
Imports a job template as a new job (admin only).

---

## AI Assistance

### Generate Job from Prompt
```
POST /ai/generate_job
```
Uses AI to generate a job definition from natural language.

**Body:**
```json
{
  "prompt": "Run a Python script that processes CSV files every hour",
  "provider": "gemini",
  "model": "gemini-pro"
}
```

### Analyze Failed Run
```
POST /ai/analyze_run
```
Uses AI to analyze a failed run and suggest fixes.

**Body:**
```json
{
  "run_id": "run_abc123",
  "stdout": "...",
  "stderr": "...",
  "exit_code": 1,
  "provider": "gemini"
}
```

---

## Events & Monitoring

### Event Stream
```
GET /events/stream
```
Server-Sent Events (SSE) stream of scheduler events.

**Events include:**
- job_submitted
- job_updated
- job_deleted
- job_enqueued
- job_scheduled
- job_paused
- job_resumed
- job_manual_run

### Run History
```
GET /history/
```
Returns all run history visible to the authenticated user.

---

## Health

### Health Check
```
GET /health
```
Returns scheduler health and basic statistics.

**Response:**
```json
{
  "status": "ok",
  "workers": 5,
  "pending_jobs": 3
}
```

---

## Authentication

All endpoints require authentication via the `x-api-key` header:

```
x-api-key: your-token-here
```

**Token Types:**
- **Admin Token**: Full access to all domains and admin endpoints
- **Domain Token**: Access limited to specific domain

Set via environment variables:
- `ADMIN_TOKEN` - Admin access token
- `WORKER_DOMAIN_TOKEN` - Domain-specific token

---

## Response Formats

### Success Response
Most endpoints return JSON with relevant data.

### Error Response
```json
{
  "detail": "Error message or validation errors"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `400` - Bad request / invalid parameters
- `403` - Forbidden / insufficient permissions
- `404` - Resource not found
- `422` - Validation error
- `500` - Internal server error

---

## Rate Limiting

No rate limiting is currently enforced, but bulk operations have the following limits:

- **Bulk Job Creation**: Max 100 jobs per request
- **Run Listing**: Max 1000 results per request

---

## CORS

CORS is enabled for origins specified in `CORS_ALLOW_ORIGINS` environment variable. Default allows:
- `http://localhost:5173` (UI dev server)
- `http://localhost:8000` (API server)
- `*` (if explicitly configured)

---

## WebSocket / SSE Endpoints

The following endpoints use Server-Sent Events (SSE) for real-time updates:

- `/events/stream` - Scheduler events
- `/runs/{run_id}/stream` - Live run logs

Connect using EventSource:
```javascript
const es = new EventSource('/events/stream?token=your-token');
es.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

---

## API Versioning

Current API version: **v1** (implicit, no version prefix required)

Future versions may be introduced with a `/v2/` prefix while maintaining backwards compatibility with v1.

---

## Examples

See `scripts/test_endpoints_manual.py` for comprehensive examples of calling all endpoints.

For frontend integration examples, see `ui/src/api/jobs.ts` and `ui/src/api/admin.ts`.
