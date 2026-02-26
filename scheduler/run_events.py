import json
import threading
import time
from datetime import datetime
from typing import Any, Dict

from .mongo_client import get_db
from .redis_client import get_redis
from .utils.logging import setup_logging
from .utils.worker_ops import append_worker_op


log = setup_logging("scheduler.run_events")


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(float(value))
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            return None
    return None


def _handle_run_start(payload: Dict[str, Any]):
    db = get_db()
    run_id = str(payload.get("run_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    if not run_id or not job_id:
        return

    start_ts = _to_datetime(payload.get("start_ts")) or datetime.utcnow()
    scheduled_ts = _to_datetime(payload.get("scheduled_ts")) or start_ts
    doc = {
        "_id": run_id,
        "job_id": job_id,
        "user": payload.get("user", ""),
        "domain": payload.get("domain", "prod"),
        "worker_id": payload.get("worker_id"),
        "start_ts": start_ts,
        "scheduled_ts": scheduled_ts,
        "end_ts": None,
        "status": "running",
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "slot": payload.get("slot"),
        "attempt": payload.get("attempt", 1),
        "retries_remaining": payload.get("retries_remaining"),
        "schedule_tick": payload.get("schedule_tick"),
        "schedule_mode": payload.get("schedule_mode"),
        "executor_type": payload.get("executor_type"),
        "queue_latency_ms": payload.get("queue_latency_ms"),
        "completion_reason": None,
        "bypass_concurrency": bool(payload.get("bypass_concurrency", False)),
    }
    db.job_runs.update_one({"_id": run_id}, {"$set": doc}, upsert=True)
    worker_id = payload.get("worker_id")
    domain = payload.get("domain", "prod")
    if worker_id:
        append_worker_op(
            domain=domain,
            worker_id=worker_id,
            op_type="run_start",
            message=f"Started job {job_id}",
            details={
                "run_id": run_id,
                "job_id": job_id,
                "slot": payload.get("slot"),
                "attempt": payload.get("attempt", 1),
            },
            ts=start_ts.timestamp(),
        )


def _handle_run_end(payload: Dict[str, Any]):
    db = get_db()
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        return

    end_ts = _to_datetime(payload.get("end_ts")) or datetime.utcnow()
    existing = db.job_runs.find_one({"_id": run_id}, {"start_ts": 1})
    start_ts = _to_datetime((existing or {}).get("start_ts")) or _to_datetime(payload.get("start_ts"))
    duration = (end_ts - start_ts).total_seconds() if start_ts else None
    update_doc = {
        "end_ts": end_ts,
        "status": payload.get("status", "failed"),
        "returncode": payload.get("returncode"),
        "stdout": payload.get("stdout", ""),
        "stderr": payload.get("stderr", ""),
        "attempt": payload.get("attempt", 1),
        "completion_reason": payload.get("completion_reason"),
        "duration": duration,
    }
    res = db.job_runs.update_one({"_id": run_id}, {"$set": update_doc})
    if res.matched_count == 0:
        # Fallback: if start event was missed, create a minimal run doc.
        db.job_runs.insert_one(
            {
                "_id": run_id,
                "job_id": payload.get("job_id", ""),
                "user": payload.get("user", ""),
                "domain": payload.get("domain", "prod"),
                "worker_id": payload.get("worker_id"),
                "start_ts": _to_datetime(payload.get("start_ts")) or end_ts,
                "scheduled_ts": _to_datetime(payload.get("scheduled_ts")) or end_ts,
                **update_doc,
                "slot": payload.get("slot"),
                "retries_remaining": payload.get("retries_remaining"),
                "schedule_tick": payload.get("schedule_tick"),
                "schedule_mode": payload.get("schedule_mode"),
                "executor_type": payload.get("executor_type"),
                "queue_latency_ms": payload.get("queue_latency_ms"),
                "bypass_concurrency": bool(payload.get("bypass_concurrency", False)),
                "duration": duration,
            }
        )

    worker_id = payload.get("worker_id")
    domain = payload.get("domain", "prod")
    if worker_id:
        append_worker_op(
            domain=domain,
            worker_id=worker_id,
            op_type="run_end",
            message=f"Finished job {payload.get('job_id', '')} ({payload.get('status', 'failed')})",
            details={
                "run_id": run_id,
                "job_id": payload.get("job_id"),
                "status": payload.get("status", "failed"),
                "returncode": payload.get("returncode"),
                "duration": duration,
                "completion_reason": payload.get("completion_reason"),
            },
            ts=end_ts.timestamp(),
        )


def _handle_event(payload: Dict[str, Any]):
    etype = str(payload.get("type") or "").strip()
    if etype == "run_start":
        _handle_run_start(payload)
    elif etype == "run_end":
        _handle_run_end(payload)


def run_event_loop(stop_event: threading.Event):
    r = get_redis()
    log.info("Run event loop started")
    while not stop_event.is_set():
        try:
            domains = list(r.smembers("hydra:domains") or []) or ["prod"]
            keys = [f"run_events:{d}" for d in domains]
            popped = r.blpop(keys, timeout=2)
            if not popped:
                continue
            key, raw = popped
            try:
                payload = json.loads(raw)
            except Exception:
                log.warning("Skipping malformed run event payload from %s", key)
                continue
            _handle_event(payload)
        except Exception as exc:
            log.exception("Error in run event loop: %s", exc)
            time.sleep(1)
