from datetime import datetime
from typing import List, Dict, Any
import time

from fastapi import APIRouter, HTTPException, Request

from ..mongo_client import get_db
from ..redis_client import get_redis
from ..models.job_definition import (
    JobCreate,
    JobDefinition,
    JobUpdate,
    JobValidationResult,
    ScheduleConfig,
)
from ..models.job_run import JobRun
from ..event_bus import event_bus
from ..utils.schedule import initialize_schedule


router = APIRouter()


def _sanitize_job_response(job: JobDefinition) -> dict:
    """Strip sensitive fields (e.g. connection_uri) from job responses."""
    data = job.model_dump(by_alias=True)
    executor = data.get("executor") or {}
    if executor.get("type") == "sql" and "connection_uri" in executor:
        executor["connection_uri"] = "********" if executor["connection_uri"] else None
    return data


def _fetch_job_runs(job_id: str, domain_filter: str | None = None) -> List[Dict[str, Any]]:
    db = get_db()
    query: Dict[str, Any] = {"job_id": job_id}
    if domain_filter:
        query["domain"] = domain_filter
    runs = list(db.job_runs.find(query).sort("start_ts", 1))
    normalized: List[Dict[str, Any]] = []
    for run in runs:
        doc = _normalize_run_doc(run)
        normalized.append(doc)
    return normalized


def _normalize_run_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(doc)
    if "_id" in normalized:
        normalized["_id"] = str(normalized["_id"])
    stdout = (normalized.get("stdout") or "")[:]
    stderr = (normalized.get("stderr") or "")[:]
    normalized["stdout_tail"] = stdout[-4096:]
    normalized["stderr_tail"] = stderr[-4096:]
    duration = None
    if normalized.get("start_ts") and normalized.get("end_ts"):
        try:
            duration = (normalized["end_ts"] - normalized["start_ts"]).total_seconds()
        except Exception:
            duration = None
    normalized["duration"] = duration
    return normalized


def _enqueue_job(job_id: str, reason: str, extra_payload: dict | None = None, priority: int | None = None, domain: str = "prod"):
    r = get_redis()
    score = float(priority if priority is not None else 5)
    r.sadd("hydra:domains", domain)
    r.zadd(f"job_queue:{domain}:pending", {job_id: score})
    r.hset(
        f"job_enqueue_meta:{domain}:{job_id}",
        mapping={"enqueued_ts": time.time(), "reason": reason},
    )
    r.expire(f"job_enqueue_meta:{domain}:{job_id}", 24 * 3600)
    payload = {"job_id": job_id, "reason": reason, "priority": score, "domain": domain}
    if extra_payload:
        payload.update(extra_payload)
    event_bus.publish("job_enqueued", payload)


def _validate_job_definition(job: JobDefinition) -> JobValidationResult:
    errors = []
    next_run_at = None
    executor = job.executor
    exec_type = getattr(executor, "type", None)
    if exec_type == "python":
        code = getattr(executor, "code", "")
        if not code.strip():
            errors.append("python executor requires non-empty code")
        else:
            try:
                compile(code, "<job>", "exec")
            except SyntaxError as exc:
                errors.append(
                    f"python code syntax error: {exc.msg} (line {exc.lineno})"
                )
        env_cfg = getattr(executor, "environment", None)
        if env_cfg and env_cfg.type != "venv" and env_cfg.venv_path:
            errors.append(
                "environment.venv_path can only be set when environment.type == 'venv'"
            )
    elif exec_type in {"shell", "batch", "powershell"}:
        script = getattr(executor, "script", "")
        if not script.strip():
            errors.append(f"{exec_type} executor requires non-empty script")
    elif exec_type == "sql":
        query = getattr(executor, "query", "")
        if not query.strip():
            errors.append("sql executor requires a non-empty query")
        connection_uri = getattr(executor, "connection_uri", None) or ""
        credential_ref = getattr(executor, "credential_ref", None) or ""
        if not connection_uri.strip() and not credential_ref.strip():
            errors.append("sql executor requires connection_uri or credential_ref")
    elif exec_type == "external":
        command = getattr(executor, "command", "")
        if not command.strip():
            errors.append("external executor requires a command or binary path")
    else:
        errors.append("executor.type must be one of python|shell|batch|powershell|sql|external")

    try:
        next_run_at = initialize_schedule(job.schedule, datetime.utcnow()).next_run_at
    except ValueError as exc:
        errors.append(str(exc))

    return JobValidationResult(valid=not errors, errors=errors, next_run_at=next_run_at)


def _attach_schedule(job_def: JobDefinition, force: bool = False) -> JobDefinition:
    schedule = job_def.schedule
    needs_init = force or (
        schedule.mode != "immediate"
        and schedule.enabled
        and schedule.next_run_at is None
    )
    if not needs_init:
        return job_def
    try:
        new_schedule = initialize_schedule(schedule, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=[str(exc)])
    return job_def.copy(update={"schedule": new_schedule})


@router.get("/jobs/")
def list_jobs(request: Request):
    db = get_db()
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    force_domain = request.query_params.get("domain")
    search = request.query_params.get("search")
    tags_param = request.query_params.get("tags")
    
    if is_admin and force_domain:
        query = {"domain": force_domain}
    elif is_admin:
        query = {}
    else:
        query = {"domain": domain}
    
    # Add search filter
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"_id": {"$regex": search, "$options": "i"}},
        ]
    
    # Add tag filter
    if tags_param:
        tags = [t.strip() for t in tags_param.split(",") if t.strip()]
        if tags:
            query["tags"] = {"$in": tags}
    
    docs = list(db.job_definitions.find(query).sort("created_at", -1))
    return [_sanitize_job_response(JobDefinition.model_validate(doc)) for doc in docs]


@router.post("/jobs/", response_model=JobDefinition)
def submit_job(job: JobCreate, request: Request):
    db = get_db()
    domain = getattr(request.state, "domain", "prod")
    payload = job.model_dump()
    payload["domain"] = domain
    job_def = JobDefinition(**payload)
    validation = _validate_job_definition(job_def)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.errors)
    job_def = _attach_schedule(job_def, force=True)
    db.job_definitions.insert_one(job_def.to_mongo())
    if job_def.schedule.mode == "immediate":
        _enqueue_job(job_def.id, reason="immediate_submit", priority=job_def.priority, domain=job_def.domain)
    event_bus.publish(
        "job_submitted",
        {
            "job_id": job_def.id,
            "name": job_def.name,
            "user": job_def.user,
            "domain": job_def.domain,
            "schedule_mode": job_def.schedule.mode,
            "next_run_at": (
                job_def.schedule.next_run_at.isoformat()
                if job_def.schedule.next_run_at
                else None
            ),
        },
    )
    return _sanitize_job_response(job_def)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    db = get_db()
    doc = db.job_definitions.find_one({"_id": job_id})
    if not doc:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and doc.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    return _sanitize_job_response(JobDefinition.model_validate(doc))


@router.get("/jobs/{job_id}/runs", response_model=List[JobRun])
def get_job_runs(job_id: str, request: Request):
    db = get_db()
    job = db.job_definitions.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    force_domain = request.query_params.get("domain")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and job.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    domain_filter = None if (is_admin and not force_domain) else (force_domain or domain)
    runs = _fetch_job_runs(job_id, domain_filter=domain_filter)
    return [JobRun.model_validate(r) for r in runs]


@router.put("/jobs/{job_id}", response_model=JobDefinition)
def update_job(job_id: str, updates: JobUpdate, request: Request):
    db = get_db()
    existing = db.job_definitions.find_one({"_id": job_id})
    if not existing:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and existing.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    update_doc = updates.model_dump(exclude_unset=True)
    if not update_doc:
        raise HTTPException(status_code=400, detail="no fields to update")
    merged = {**existing, **update_doc}
    merged["updated_at"] = datetime.utcnow()
    job_def = JobDefinition.model_validate(merged)
    validation = _validate_job_definition(job_def)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.errors)
    job_def = _attach_schedule(job_def, force="schedule" in update_doc)
    db.job_definitions.replace_one({"_id": job_id}, job_def.to_mongo())
    event_bus.publish("job_updated", {"job_id": job_id, "domain": job_def.domain})
    return _sanitize_job_response(job_def)


@router.post("/jobs/{job_id}/validate", response_model=JobValidationResult)
def validate_job(job_id: str, request: Request):
    db = get_db()
    doc = db.job_definitions.find_one({"_id": job_id})
    if not doc:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and doc.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    job_def = JobDefinition.model_validate(doc)
    return _validate_job_definition(job_def)


@router.post("/jobs/validate", response_model=JobValidationResult)
def validate_payload(job: JobCreate, request: Request):
    domain = getattr(request.state, "domain", "prod")
    payload = job.model_dump()
    payload["domain"] = domain
    job_def = JobDefinition(**payload)
    return _validate_job_definition(job_def)


@router.post("/jobs/{job_id}/run")
def run_job_now(job_id: str, request: Request):
    db = get_db()
    doc = db.job_definitions.find_one({"_id": job_id})
    if not doc:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and doc.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    priority = doc.get("priority", 5)
    _enqueue_job(job_id, reason="manual_run", priority=priority, domain=doc.get("domain", "prod"))
    event_bus.publish("job_manual_run", {"job_id": job_id, "domain": doc.get("domain", "prod")})
    return {"job_id": job_id, "queued": True}


@router.post("/jobs/adhoc", response_model=JobDefinition)
def run_adhoc_job(job: JobCreate, request: Request):
    db = get_db()
    domain = getattr(request.state, "domain", "prod")
    adhoc_schedule = ScheduleConfig(mode="immediate", enabled=False)
    job_dict = job.model_dump()
    job_dict["schedule"] = adhoc_schedule.model_dump()
    job_dict["domain"] = domain
    job_def = JobDefinition(**job_dict)
    validation = _validate_job_definition(job_def)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.errors)
    job_def = _attach_schedule(job_def, force=True)
    db.job_definitions.insert_one(job_def.to_mongo())
    _enqueue_job(job_def.id, reason="adhoc_run", priority=job_def.priority, domain=domain)
    return _sanitize_job_response(job_def)


@router.get("/overview/jobs")
def jobs_overview(request: Request):
    db = get_db()
    r = get_redis()
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    force_domain = request.query_params.get("domain")
    if is_admin and force_domain:
        query = {"domain": force_domain}
    elif is_admin:
        query = {}
    else:
        query = {"domain": domain}
    job_docs = list(db.job_definitions.find(query))
    overview = []
    for job in job_docs:
        job_id = job["_id"]
        total_runs = db.job_runs.count_documents({"job_id": job_id})
        success_runs = db.job_runs.count_documents(
            {"job_id": job_id, "status": "success"}
        )
        failed_runs = db.job_runs.count_documents(
            {"job_id": job_id, "status": "failed"}
        )
        queued = 1 if r.zscore(f"job_queue:{job.get('domain','prod')}:pending", job_id) is not None else 0
        recent_runs_cursor = (
            db.job_runs.find({"job_id": job_id})
            .sort("start_ts", -1)
            .limit(12)
        )
        recent_runs = [_normalize_run_doc(run) for run in recent_runs_cursor]
        last_run_doc = recent_runs[0] if recent_runs else None
        
        # Calculate average duration from successful runs
        avg_duration = None
        completed_runs = list(db.job_runs.find(
            {"job_id": job_id, "status": {"$in": ["success", "failed"]}, "duration": {"$ne": None}}
        ).limit(10))
        if completed_runs:
            durations = [run.get("duration", 0) for run in completed_runs if run.get("duration") is not None]
            if durations:
                avg_duration = sum(durations) / len(durations)
        
        # Get last failure reason
        last_failure_reason = None
        if failed_runs > 0:
            last_failed = db.job_runs.find_one(
                {"job_id": job_id, "status": "failed"},
                sort=[("start_ts", -1)]
            )
            if last_failed:
                last_failure_reason = last_failed.get("completion_reason")
        
        overview.append(
            {
                "job_id": job_id,
                "name": job.get("name", ""),
                "schedule_mode": (job.get("schedule") or {}).get("mode", "immediate"),
                "tags": job.get("tags", []),
                "total_runs": total_runs,
                "success_runs": success_runs,
                "failed_runs": failed_runs,
                "queued_runs": queued,
                "last_run": last_run_doc,
                "recent_runs": recent_runs,
                "avg_duration_seconds": avg_duration,
                "last_failure_reason": last_failure_reason,
            }
        )
    return overview


def _serialize_ts(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@router.get("/jobs/{job_id}/grid")
def job_grid(job_id: str, request: Request):
    db = get_db()
    job = db.job_definitions.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and job.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    force_domain = request.query_params.get("domain")
    runs = _fetch_job_runs(job_id, domain_filter=None if (is_admin and not force_domain) else (force_domain or domain))
    task_id = "task_main"
    tasks = [
        {
            "task_id": task_id,
            "label": job.get("name", task_id),
            "instances": [
                {
                    "run_id": run["_id"],
                    "status": run.get("status"),
                    "start_ts": _serialize_ts(run.get("start_ts")),
                    "end_ts": _serialize_ts(run.get("end_ts")),
                    "duration": run.get("duration"),
                }
                for run in runs
            ],
        }
    ]
    run_summary = [
        {
            "run_id": run["_id"],
            "status": run.get("status"),
            "start_ts": _serialize_ts(run.get("start_ts")),
            "end_ts": _serialize_ts(run.get("end_ts")),
            "duration": run.get("duration"),
        }
        for run in runs
    ]
    return {"tasks": tasks, "runs": run_summary}


@router.get("/jobs/{job_id}/gantt")
def job_gantt(job_id: str, request: Request):
    db = get_db()
    job = db.job_definitions.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and job.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    force_domain = request.query_params.get("domain")
    runs = _fetch_job_runs(job_id, domain_filter=None if (is_admin and not force_domain) else (force_domain or domain))
    entries = [
        {
            "run_id": run["_id"],
            "start_ts": _serialize_ts(run.get("start_ts")),
            "end_ts": _serialize_ts(run.get("end_ts")),
            "duration": run.get("duration"),
            "status": run.get("status"),
        }
        for run in runs
    ]
    return {"entries": entries}


@router.get("/jobs/{job_id}/graph")
def job_graph(job_id: str, request: Request):
    db = get_db()
    job = db.job_definitions.find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    if not is_admin and job.get("domain", "prod") != domain:
        raise HTTPException(status_code=403, detail="forbidden")
    force_domain = request.query_params.get("domain")
    runs = _fetch_job_runs(job_id, domain_filter=None if (is_admin and not force_domain) else (force_domain or domain))
    last_status = runs[-1]["status"] if runs else "unknown"
    nodes = [
        {
            "id": job_id,
            "label": job.get("name", job_id),
            "status": last_status,
        }
    ]
    edges: List[Dict[str, Any]] = []
    return {"nodes": nodes, "edges": edges}


@router.get("/overview/statistics")
def jobs_statistics(request: Request):
    """Get aggregate statistics across all jobs"""
    db = get_db()
    r = get_redis()
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    force_domain = request.query_params.get("domain")
    
    if is_admin and force_domain:
        query = {"domain": force_domain}
    elif is_admin:
        query = {}
    else:
        query = {"domain": domain}
    
    total_jobs = db.job_definitions.count_documents(query)
    
    # Count jobs by schedule mode
    cron_jobs = db.job_definitions.count_documents({**query, "schedule.mode": "cron"})
    interval_jobs = db.job_definitions.count_documents({**query, "schedule.mode": "interval"})
    immediate_jobs = db.job_definitions.count_documents({**query, "schedule.mode": "immediate"})
    
    # Count enabled vs disabled
    enabled_jobs = db.job_definitions.count_documents({**query, "schedule.enabled": True})
    disabled_jobs = total_jobs - enabled_jobs
    
    # Run statistics
    run_query = query.copy() if "domain" in query else {}
    if "domain" in run_query:
        run_query = {"domain": run_query["domain"]}
    
    total_runs = db.job_runs.count_documents(run_query)
    success_runs = db.job_runs.count_documents({**run_query, "status": "success"})
    failed_runs = db.job_runs.count_documents({**run_query, "status": "failed"})
    running_runs = db.job_runs.count_documents({**run_query, "status": "running"})
    
    # Get unique tags
    all_jobs = list(db.job_definitions.find(query, {"tags": 1}))
    all_tags = set()
    for job in all_jobs:
        all_tags.update(job.get("tags", []))
    
    return {
        "total_jobs": total_jobs,
        "schedule_breakdown": {
            "cron": cron_jobs,
            "interval": interval_jobs,
            "immediate": immediate_jobs,
        },
        "enabled_jobs": enabled_jobs,
        "disabled_jobs": disabled_jobs,
        "total_runs": total_runs,
        "success_runs": success_runs,
        "failed_runs": failed_runs,
        "running_runs": running_runs,
        "success_rate": (success_runs / total_runs * 100) if total_runs > 0 else 0,
        "available_tags": sorted(list(all_tags)),
    }
