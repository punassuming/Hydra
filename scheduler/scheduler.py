import os
import threading
import time
import hashlib
import json
from datetime import datetime
from typing import Dict, List

from pymongo import ReturnDocument

from .redis_client import get_redis
from .mongo_client import get_db
from .utils.affinity import passes_affinity
from .utils.selectors import select_best_worker
from .utils.failover import failover_once
from .utils.logging import setup_logging
from .utils.worker_ops import append_worker_op
from .event_bus import event_bus
from .models.job_definition import ScheduleConfig
from .utils.schedule import advance_schedule
from .utils.encryption import decrypt_payload


log = setup_logging("scheduler")


def _json_ready(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    return value


def _resolve_credential_refs(job: dict, db) -> dict:
    """If the job's executor or source uses credential_ref, resolve it.

    For SQL executors: resolves credential_ref to connection_uri.
    For HTTP executors: resolves credential_ref to Authorization header.
    For git sources: resolves credential_ref to a token injected into the source.

    This injects decrypted credentials into the job dict so the worker
    (which is Redis-only and has no access to MongoDB) can connect.
    The original job document in Mongo is never mutated.
    Credentials are domain-scoped: only credentials belonging to the
    same domain as the job are resolved.
    """
    job_domain = job.get("domain", "prod")

    # Resolve SQL executor credential_ref
    executor = job.get("executor") or {}
    if executor.get("type") == "sql":
        credential_ref = (executor.get("credential_ref") or "").strip()
        if credential_ref and not (executor.get("connection_uri") or "").strip():
            cred_doc = db.credentials.find_one({"name": credential_ref, "domain": job_domain})
            if not cred_doc:
                log.warning("credential_ref '%s' not found for job %s in domain %s", credential_ref, job.get("_id"), job_domain)
            else:
                try:
                    decrypted = decrypt_payload(cred_doc["encrypted_payload"])
                    # Build connection_uri from decrypted payload
                    resolved_uri = decrypted.get("connection_uri") or ""
                    if not resolved_uri and decrypted.get("host"):
                        dialect = executor.get("dialect", "postgres")
                        user = decrypted.get("username", "")
                        password = decrypted.get("password", "")
                        host = decrypted.get("host", "localhost")
                        port = decrypted.get("port", "")
                        database = decrypted.get("database") or executor.get("database", "")
                        auth = f"{user}:{password}@" if user else ""
                        port_part = f":{port}" if port else ""
                        db_part = f"/{database}" if database else ""
                        dialect_map = {
                            "postgres": "postgresql",
                            "mysql": "mysql+pymysql",
                            "mssql": "mssql+pyodbc",
                            "oracle": "oracle+cx_oracle",
                            "mongodb": "mongodb",
                        }
                        scheme = dialect_map.get(dialect, dialect)
                        resolved_uri = f"{scheme}://{auth}{host}{port_part}{db_part}"
                    if resolved_uri:
                        job = {**job, "executor": {**executor, "connection_uri": resolved_uri}}
                except Exception:
                    log.exception("Failed to decrypt credential '%s' for job %s", credential_ref, job.get("_id"))

    # Resolve HTTP executor credential_ref → inject Authorization header
    if executor.get("type") == "http":
        credential_ref = (executor.get("credential_ref") or "").strip()
        if credential_ref:
            cred_doc = db.credentials.find_one({"name": credential_ref, "domain": job_domain})
            if not cred_doc:
                log.warning("credential_ref '%s' not found for http job %s in domain %s", credential_ref, job.get("_id"), job_domain)
            else:
                try:
                    decrypted = decrypt_payload(cred_doc["encrypted_payload"])
                    # Support token (Bearer), api_key (X-API-Key), or username:password (Basic)
                    headers = dict(executor.get("headers") or {})
                    if decrypted.get("token"):
                        headers["Authorization"] = f"Bearer {decrypted['token']}"
                    elif decrypted.get("api_key"):
                        headers["X-API-Key"] = decrypted["api_key"]
                    elif decrypted.get("username") and decrypted.get("password"):
                        import base64
                        creds = base64.b64encode(f"{decrypted['username']}:{decrypted['password']}".encode()).decode()
                        headers["Authorization"] = f"Basic {creds}"
                    job = {**job, "executor": {**executor, "headers": headers}}
                except Exception:
                    log.exception("Failed to decrypt credential '%s' for http job %s", credential_ref, job.get("_id"))

    # Resolve source credential_ref (git PAT)
    source = job.get("source") or {}
    src_credential_ref = (source.get("credential_ref") or "").strip()
    if src_credential_ref and not source.get("token"):
        cred_doc = db.credentials.find_one({"name": src_credential_ref, "domain": job_domain})
        if not cred_doc:
            log.warning("source credential_ref '%s' not found for job %s in domain %s", src_credential_ref, job.get("_id"), job_domain)
        else:
            try:
                decrypted = decrypt_payload(cred_doc["encrypted_payload"])
                token = decrypted.get("token") or decrypted.get("password") or ""
                if token:
                    job = {**job, "source": {**source, "token": token}}
            except Exception:
                log.exception("Failed to decrypt source credential '%s' for job %s", src_credential_ref, job.get("_id"))

    return job


def list_online_workers(ttl_seconds: int, domain: str, respect_capacity: bool = True) -> List[Dict]:
    r = get_redis()
    now = time.time()
    workers: List[Dict] = []
    for key in r.scan_iter(f"workers:{domain}:*"):
        parts = key.split(":")
        worker_id = parts[2] if len(parts) > 2 else parts[-1]
        data = r.hgetall(key)
        hb = r.zscore(f"worker_heartbeats:{domain}", worker_id) or 0
        # Determine online by TTL
        online = (now - hb) <= ttl_seconds
        if not online:
            continue
        expected_hash = r.get(f"token_hash:{domain}")
        worker_hash = data.get("domain_token_hash")
        if expected_hash and worker_hash and worker_hash != expected_hash:
            continue
        worker = {
            "worker_id": worker_id,
            "os": data.get("os", ""),
            "tags": (data.get("tags", "") or "").split(",") if data.get("tags") else [],
            "allowed_users": (data.get("allowed_users", "") or "").split(",") if data.get("allowed_users") else [],
            "max_concurrency": int(data.get("max_concurrency", 1)),
            "current_running": int(data.get("current_running", 0)),
            "hostname": data.get("hostname", ""),
            "ip": data.get("ip", ""),
            "subnet": data.get("subnet", ""),
            "deployment_type": data.get("deployment_type", ""),
            "state": data.get("state", "online"),
            "capabilities": (data.get("capabilities", "") or "").split(",") if data.get("capabilities") else [],
        }
        # Only accept workers with available slots
        if worker["state"] != "online":
            continue
        if (not respect_capacity) or (worker["current_running"] < worker["max_concurrency"]):
            workers.append(worker)
    return workers


def scheduling_loop(stop_event: threading.Event):
    r = get_redis()
    db = get_db()
    ttl = int(os.getenv("SCHEDULER_HEARTBEAT_TTL", "10"))
    log.info("Scheduling loop started (heartbeat TTL=%ss)", ttl)
    while not stop_event.is_set():
        try:
            domains = list(r.smembers("hydra:domains") or []) or ["prod"]
            pending_keys = [f"job_queue:{d}:pending" for d in domains]
            popped = r.bzpopmax(pending_keys, timeout=2)
            if not popped:
                continue
            key, job_id, _score = popped
            domain = key.split(":")[1] if ":" in key else "prod"
            job = db.job_definitions.find_one({"_id": job_id})
            if not job:
                log.error("Received job_id %s with no definition; skipping", job_id)
                continue
            domain = job.get("domain", domain)
            bypass_concurrency = bool(job.get("bypass_concurrency", False))
            meta_key = f"job_enqueue_meta:{domain}:{job_id}"
            meta = r.hgetall(meta_key) or {}
            enqueued_ts = float(meta.get("enqueued_ts", time.time()))
            enqueue_reason = meta.get("reason")
            retry_attempt = int(meta.get("retry_attempt", 0))
            r.delete(meta_key)
            candidates = [
                w
                for w in list_online_workers(ttl, domain, respect_capacity=not bypass_concurrency)
                if passes_affinity(job, w)
            ]
            worker = select_best_worker(candidates)
            if not worker:
                # No worker matches; requeue and backoff
                log.warning("No eligible worker for job %s; requeuing", job_id)
                r.zadd(f"job_queue:{domain}:pending", {job_id: float(job.get("priority", 5))})
                r.hset(
                    meta_key,
                    mapping={
                        "enqueued_ts": enqueued_ts,
                        "reason": enqueue_reason or "no_worker",
                    },
                )
                r.expire(meta_key, 24 * 3600)
                event_bus.publish("job_pending", {"job_id": job_id, "reason": "no_worker", "domain": domain})
                time.sleep(1)
                continue
            wid = worker["worker_id"]
            dispatched_job = _resolve_credential_refs(job, db)
            params_raw = meta.get("params")
            params = json.loads(params_raw) if params_raw else {}
            envelope = {
                "job_id": job_id,
                "domain": domain,
                "job": _json_ready(dispatched_job),
                "enqueued_ts": enqueued_ts,
                "dispatch_ts": time.time(),
                "enqueue_reason": enqueue_reason,
                "retry_attempt": retry_attempt,
                "params": params,
            }
            r.rpush(f"job_queue:{domain}:{wid}", json.dumps(envelope))
            append_worker_op(
                domain=domain,
                worker_id=wid,
                op_type="dispatch",
                message=f"Job {job_id} dispatched",
                details={
                    "job_id": job_id,
                    "bypass_concurrency": bypass_concurrency,
                    "enqueue_reason": enqueue_reason,
                },
            )
            # Mark a pending run exists (worker updates on start)
            event_bus.publish(
                "job_dispatched",
                {
                    "job_id": job_id,
                    "worker_id": wid,
                    "domain": domain,
                    "bypass_concurrency": bypass_concurrency,
                },
            )
            log.info("Dispatched job %s to worker %s (bypass_concurrency=%s)", job_id, wid, bypass_concurrency)
        except Exception as e:
            log.exception("Error in scheduling loop: %s", e)
            time.sleep(1)


def failover_loop(stop_event: threading.Event):
    ttl = int(os.getenv("SCHEDULER_HEARTBEAT_TTL", "10"))
    log.info("Failover loop started (TTL=%ss)", ttl)
    while not stop_event.is_set():
        try:
            failover_once(ttl)
        except Exception as e:
            log.exception("Error in failover loop: %s", e)
        time.sleep(2)


def schedule_trigger_loop(stop_event: threading.Event):
    r = get_redis()
    db = get_db()
    log.info("Schedule trigger loop started")
    while not stop_event.is_set():
        try:
            now = datetime.utcnow()
            domains = list(r.smembers("hydra:domains") or []) or ["prod"]
            for domain in domains:
                due_jobs = db.job_definitions.find(
                    {
                        "domain": domain,
                        "schedule.mode": {"$in": ["cron", "interval"]},
                        "schedule.enabled": True,
                        "schedule.next_run_at": {"$ne": None, "$lte": now},
                    }
                ).limit(100)
                for job in due_jobs:
                    schedule_doc = job.get("schedule") or {}
                    next_run_at = schedule_doc.get("next_run_at")
                    if not next_run_at:
                        continue
                    schedule = ScheduleConfig.model_validate(schedule_doc)
                    advanced = advance_schedule(schedule)
                    updated = db.job_definitions.find_one_and_update(
                        {
                            "_id": job["_id"],
                            "schedule.next_run_at": next_run_at,
                        },
                        {"$set": {"schedule": advanced.model_dump(by_alias=True)}},
                        return_document=ReturnDocument.AFTER,
                    )
                    if not updated:
                        continue
                    priority = int(job.get("priority", 5))
                    r.zadd(f"job_queue:{domain}:pending", {job["_id"]: priority})
                    event_bus.publish(
                        "job_scheduled",
                        {
                            "job_id": job["_id"],
                            "mode": schedule.mode,
                            "next_run_at": advanced.next_run_at.isoformat() if advanced.next_run_at else None,
                            "domain": domain,
                        },
                    )
        except Exception as exc:
            log.exception("Error in schedule trigger loop: %s", exc)
            time.sleep(1)
        time.sleep(1)


def timeout_enforcement_loop(stop_event: threading.Event):
    r = get_redis()
    db = get_db()
    log.info("Timeout enforcement loop started")
    while not stop_event.is_set():
        try:
            now = time.time()
            domains = list(r.smembers("hydra:domains") or []) or ["prod"]
            for domain in domains:
                for key in r.scan_iter(f"job_running:{domain}:*"):
                    data = r.hgetall(key) or {}
                    job_id = key.split(":")[-1]
                    run_id = data.get("run_id")
                    if not run_id:
                        continue
                    started_ts = float(data.get("heartbeat", now))
                    elapsed = now - started_ts
                    job_doc = db.job_definitions.find_one({"_id": job_id}, {"timeout": 1})
                    if not job_doc:
                        continue
                    job_timeout = int(job_doc.get("timeout", 0))
                    if job_timeout > 0 and elapsed > job_timeout:
                        log.warning(
                            "Timeout exceeded for job %s run %s (%.1fs > %ss); sending kill signal",
                            job_id, run_id, elapsed, job_timeout,
                        )
                        r.publish(f"job_kill:{domain}", run_id)
        except Exception as exc:
            log.exception("Error in timeout enforcement loop: %s", exc)
        time.sleep(5)
