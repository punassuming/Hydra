import os
import time
from datetime import datetime
from typing import List, Tuple

from ..redis_client import get_redis
from ..mongo_client import get_db
from .logging import setup_logging
from .worker_ops import append_worker_op
from ..event_bus import event_bus


log = setup_logging("scheduler.failover")


def find_offline_workers(ttl_seconds: int) -> List[Tuple[str, float]]:
    r = get_redis()
    now = time.time()
    offline = []
    # Get all workers with heartbeat older than TTL per domain
    for key in r.scan_iter("worker_heartbeats:*"):
        domain = key.split(":")[1]
        heartbeats = r.zrange(key, 0, -1, withscores=True)
        for worker_id, ts in heartbeats:
            age = now - ts
            if age > ttl_seconds:
                offline.append((f"{domain}:{worker_id}", age))
    return offline


def requeue_jobs_for_worker(domain_and_worker: str):
    r = get_redis()
    db = get_db()
    domain, worker_id = domain_and_worker.split(":", 1)
    set_key = f"worker_running_set:{domain}:{worker_id}"
    job_ids = r.smembers(set_key) or []
    if job_ids:
        log.warning("Requeuing %d job(s) from offline worker %s", len(job_ids), worker_id)
        append_worker_op(
            domain=domain,
            worker_id=worker_id,
            op_type="failover",
            message=f"Worker heartbeat expired; requeuing {len(job_ids)} running job(s)",
            details={"requeued_jobs": list(job_ids)},
        )
    for job_id in job_ids:
        # Clean running markers and requeue
        running_info = r.hgetall(f"job_running:{domain}:{job_id}") or {}
        run_id = running_info.get("run_id")
        if run_id:
            db.job_runs.update_one(
                {"_id": run_id, "status": "running"},
                {
                    "$set": {
                        "status": "failed",
                        "completion_reason": "worker offline; job requeued",
                        "end_ts": datetime.utcnow(),
                    }
                },
            )
        r.delete(f"job_running:{domain}:{job_id}")
        r.zadd(f"job_queue:{domain}:pending", {job_id: 5})
        r.hset(
            f"job_enqueue_meta:{domain}:{job_id}",
            mapping={"enqueued_ts": time.time(), "reason": "failover_requeue"},
        )
        r.expire(f"job_enqueue_meta:{domain}:{job_id}", 24 * 3600)
        r.srem(set_key, job_id)
        event_bus.publish("job_requeued", {"job_id": job_id, "worker_id": worker_id, "domain": domain})
        # Optionally update last run doc to pending again (leave as is; worker will update when rerun)
    # Reset current_running counter to 0
    r.hset(f"workers:{domain}:{worker_id}", mapping={"current_running": 0, "status": "offline"})
    append_worker_op(
        domain=domain,
        worker_id=worker_id,
        op_type="connectivity",
        message="Worker marked offline by failover",
        details={"ttl_expired": True},
    )


def prune_stale_worker(domain_and_worker: str, age_seconds: float):
    r = get_redis()
    domain, worker_id = domain_and_worker.split(":", 1)
    # Keep operational timeline key for debugging; remove active registry/state keys.
    r.delete(
        f"workers:{domain}:{worker_id}",
        f"worker_running_set:{domain}:{worker_id}",
        f"worker_metrics:{domain}:{worker_id}:history",
    )
    r.zrem(f"worker_heartbeats:{domain}", worker_id)
    append_worker_op(
        domain=domain,
        worker_id=worker_id,
        op_type="prune",
        message="Pruned stale offline worker record",
        details={"offline_age_seconds": round(age_seconds, 1)},
    )
    log.info("Pruned stale worker record %s (offline %.1fs)", domain_and_worker, age_seconds)


def failover_once(ttl_seconds: int):
    r = get_redis()
    prune_after = max(ttl_seconds * 3, int(os.getenv("SCHEDULER_WORKER_OFFLINE_PRUNE_SECONDS", "1800")))
    handled_ttl = max(10, ttl_seconds * 2)
    offline_workers = find_offline_workers(ttl_seconds)
    for wid, age in offline_workers:
        domain, worker_id = wid.split(":", 1)
        running_key = f"worker_running_set:{domain}:{worker_id}"
        worker_queue_key = f"job_queue:{domain}:{worker_id}"

        if age >= prune_after and not (r.smembers(running_key) or []) and int(r.llen(worker_queue_key) or 0) == 0:
            prune_stale_worker(wid, age)
            continue

        marker_key = f"worker_failover_handled:{domain}:{worker_id}"
        # Avoid repeatedly re-processing the same offline worker every loop.
        first_seen = bool(r.set(marker_key, str(int(time.time())), nx=True, ex=handled_ttl))
        if first_seen:
            requeue_jobs_for_worker(wid)
