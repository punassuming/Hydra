import json
from fastapi import APIRouter, Request, HTTPException
from typing import List

from ..redis_client import get_redis
from ..models.worker_info import WorkerInfo

router = APIRouter()


def _metrics_summary(r, domain: str, worker_id: str, data: dict) -> dict:
    """
    Return current + rolling 30m maxima from Redis history maintained by worker heartbeat.
    """
    history_key = f"worker_metrics:{domain}:{worker_id}:history"
    raw_points = r.lrange(history_key, -180, -1) or []
    samples = []
    for raw in raw_points:
        try:
            samples.append(json.loads(raw))
        except Exception:
            continue

    if not samples:
        memory_rss_mb = None
        process_count = None
        metrics_ts = None
        try:
            if data.get("memory_rss_mb") not in (None, ""):
                memory_rss_mb = float(data.get("memory_rss_mb"))
            if data.get("process_count") not in (None, ""):
                process_count = int(data.get("process_count"))
            if data.get("metrics_ts") not in (None, ""):
                metrics_ts = float(data.get("metrics_ts"))
        except Exception:
            pass
        return {
            "memory_rss_mb": memory_rss_mb,
            "process_count": process_count,
            "memory_rss_mb_max_30m": memory_rss_mb,
            "process_count_max_30m": process_count,
            "metrics_updated_at": metrics_ts,
        }

    latest = samples[-1]
    mem_values = [
        float(s.get("memory_rss_mb"))
        for s in samples
        if s.get("memory_rss_mb") is not None
    ]
    proc_values = [
        int(s.get("process_count"))
        for s in samples
        if s.get("process_count") is not None
    ]
    return {
        "memory_rss_mb": float(latest.get("memory_rss_mb")) if latest.get("memory_rss_mb") is not None else None,
        "process_count": int(latest.get("process_count")) if latest.get("process_count") is not None else None,
        "memory_rss_mb_max_30m": max(mem_values) if mem_values else None,
        "process_count_max_30m": max(proc_values) if proc_values else None,
        "metrics_updated_at": float(latest.get("ts")) if latest.get("ts") is not None else None,
    }


@router.get("/workers/", response_model=List[WorkerInfo])
def list_workers(request: Request):
    r = get_redis()
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    force_domain = request.query_params.get("domain")
    workers = []
    if is_admin and not force_domain:
        domains = [key.split(":")[1] for key in r.scan_iter("workers:*") if key.count(":") >= 2]
    else:
        domains = [force_domain or domain]
    domains = list(set(domains))
    if not domains:
        domains = [domain]
    for dom in domains:
        for key in r.scan_iter(f"workers:{dom}:*"):
            parts = key.split(":")
            wid = parts[2] if len(parts) > 2 else parts[-1]
            data = r.hgetall(key)
            metrics = _metrics_summary(r, dom, wid, data)
            hb = r.zscore(f"worker_heartbeats:{dom}", wid)
            running_jobs = list(r.smembers(f"worker_running_set:{dom}:{wid}") or [])
            workers.append(
                WorkerInfo(
                    worker_id=wid,
                    domain=dom,
                    os=data.get("os", ""),
                    tags=(data.get("tags", "") or "").split(",") if data.get("tags") else [],
                    allowed_users=(data.get("allowed_users", "") or "").split(",") if data.get("allowed_users") else [],
                    max_concurrency=int(data.get("max_concurrency", 1)),
                    current_running=int(data.get("current_running", 0)),
                    last_heartbeat=hb,
                    status=data.get("status", "online"),
                    state=data.get("state", "online"),
                    cpu_count=int(data.get("cpu_count", 0)) or None,
                    python_version=data.get("python_version"),
                    cwd=data.get("cwd"),
                    hostname=data.get("hostname"),
                    ip=data.get("ip"),
                    subnet=data.get("subnet"),
                    deployment_type=data.get("deployment_type"),
                    run_user=data.get("run_user"),
                    process_count=metrics["process_count"],
                    memory_rss_mb=metrics["memory_rss_mb"],
                    process_count_max_30m=metrics["process_count_max_30m"],
                    memory_rss_mb_max_30m=metrics["memory_rss_mb_max_30m"],
                    metrics_updated_at=metrics["metrics_updated_at"],
                    running_jobs=running_jobs,
                )
            )
    return workers


@router.post("/workers/{worker_id}/state")
def set_worker_state(worker_id: str, state: str, request: Request):
    """
    Set worker state to online|draining|disabled.
    Draining/disabled will prevent new dispatches; running jobs continue.
    """
    state = state.lower()
    if state not in {"online", "draining", "disabled"}:
        return {"ok": False, "error": "invalid state"}
    r = get_redis()
    domain = getattr(request.state, "domain", "prod")
    is_admin = getattr(request.state, "is_admin", False)
    key = f"workers:{domain}:{worker_id}"
    if not r.exists(key):
        if not is_admin:
            return {"ok": False, "error": "worker not found"}
        # allow admin to target any domain via query param ?domain=
        alt_domain = request.query_params.get("domain")
        if alt_domain and r.exists(f"workers:{alt_domain}:{worker_id}"):
            domain = alt_domain
            key = f"workers:{domain}:{worker_id}"
        else:
            return {"ok": False, "error": "worker not found"}
    r.hset(key, mapping={"state": state})
    return {"ok": True, "state": state}
