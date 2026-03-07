import os
import threading
import time
import hashlib
import json
import uuid
import urllib.request
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

# Maximum time (in seconds) for a single HTTP sensor request. Capped well below
# the minimum poll_interval so that a slow check doesn't block the next interval.
_HTTP_REQUEST_MAX_TIMEOUT_SECONDS = 25

# Cadence (seconds) of the outer sensor evaluation loop.
_SENSOR_LOOP_SLEEP_SECONDS = 5

# SQLAlchemy URL scheme mapping used when building a connection URI from credential fields.
_SQL_DIALECT_MAP = {
    "postgres": "postgresql",
    "mysql": "mysql+pymysql",
    "mssql": "mssql+pyodbc",
    "oracle": "oracle+cx_oracle",
    "mongodb": "mongodb",
}


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

            # Route sensor jobs to the internal sensor evaluation loop
            executor = job.get("executor") or {}
            if executor.get("type") == "sensor":
                _activate_sensor(r, job, domain, enqueued_ts, enqueue_reason)
                log.info("Routed sensor job %s to sensor evaluation loop", job_id)
                continue

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


def sla_monitoring_loop(stop_event: threading.Event):
    from .run_events import _fire_webhooks_async, _fire_email_alert_async
    db = get_db()
    log.info("SLA monitoring loop started")
    while not stop_event.is_set():
        try:
            now = datetime.utcnow()
            cursor = db.job_runs.find(
                {"status": "running", "sla_miss_alerted": {"$ne": True}},
                {"_id": 1, "job_id": 1, "domain": 1, "start_ts": 1},
            )
            for run_doc in cursor:
                run_id = run_doc.get("_id")
                job_id = run_doc.get("job_id")
                domain = run_doc.get("domain", "prod")
                start_ts = run_doc.get("start_ts")
                if not start_ts or not job_id:
                    continue
                if not isinstance(start_ts, datetime):
                    try:
                        start_ts = datetime.fromisoformat(str(start_ts))
                    except Exception:
                        continue
                elapsed = (now - start_ts).total_seconds()
                job_doc = db.job_definitions.find_one(
                    {"_id": job_id},
                    {"sla_max_duration_seconds": 1, "on_failure_webhooks": 1, "on_failure_email_to": 1, "on_failure_email_credential_ref": 1},
                )
                if not job_doc:
                    continue
                sla_seconds = job_doc.get("sla_max_duration_seconds")
                try:
                    sla_seconds = int(sla_seconds) if sla_seconds is not None else 0
                except (TypeError, ValueError):
                    continue
                if sla_seconds <= 0:
                    continue
                if elapsed > sla_seconds:
                    result = db.job_runs.update_one(
                        {"_id": run_id, "sla_miss_alerted": {"$ne": True}},
                        {"$set": {"sla_miss_alerted": True}},
                    )
                    if result.modified_count == 0:
                        continue
                    log.warning(
                        "SLA missed for job %s run %s (%.1fs > %ss); firing alerts",
                        job_id, run_id, elapsed, sla_seconds,
                    )
                    alert_message = (
                        f"SLA Warning: Job exceeded expected duration of {sla_seconds} seconds "
                        f"(running for {elapsed:.1f}s)"
                    )
                    webhooks = job_doc.get("on_failure_webhooks") or []
                    _fire_webhooks_async(webhooks, job_id, run_id, alert_message)
                    email_to = job_doc.get("on_failure_email_to") or []
                    email_cred_ref = str(job_doc.get("on_failure_email_credential_ref") or "").strip()
                    _fire_email_alert_async(db, domain, email_cred_ref, email_to, job_id, run_id, alert_message)
        except Exception as exc:
            log.exception("Error in SLA monitoring loop: %s", exc)
        time.sleep(30)


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


def backfill_dispatch_loop(stop_event: threading.Event):
    """Process backfill queue items and dispatch them to available workers.

    Each item in ``backfill_queue:{domain}`` (a Redis list) is a JSON object
    with ``job_id``, ``execution_date``, ``priority``, and ``domain``.  For
    each item, the loop selects an available worker using the same affinity and
    capacity rules as the main scheduling loop, then pushes a job envelope to
    the worker's queue with ``HYDRA_EXECUTION_DATE`` and ``HYDRA_IS_BACKFILL``
    injected as runtime parameters (env vars).
    """
    r = get_redis()
    db = get_db()
    ttl = int(os.getenv("SCHEDULER_HEARTBEAT_TTL", "10"))
    log.info("Backfill dispatch loop started (heartbeat TTL=%ss)", ttl)
    while not stop_event.is_set():
        try:
            domains = list(r.smembers("hydra:domains") or []) or ["prod"]
            backfill_keys = [f"backfill_queue:{d}" for d in domains]
            popped = r.blpop(backfill_keys, timeout=2)
            if not popped:
                continue
            _key, raw = popped
            try:
                item = json.loads(raw)
            except Exception:
                log.warning("Invalid backfill queue item (not JSON): %s", raw)
                continue

            job_id = item.get("job_id", "")
            execution_date = item.get("execution_date", "")
            domain = item.get("domain", "prod")
            priority = float(item.get("priority", 5))

            if not job_id or not execution_date:
                log.warning("Backfill item missing job_id or execution_date; skipping")
                continue

            job = db.job_definitions.find_one({"_id": job_id})
            if not job:
                log.error("Backfill: job_id %s not found; skipping date %s", job_id, execution_date)
                continue

            domain = job.get("domain", domain)
            bypass_concurrency = bool(job.get("bypass_concurrency", False))

            candidates = [
                w
                for w in list_online_workers(ttl, domain, respect_capacity=not bypass_concurrency)
                if passes_affinity(job, w)
            ]
            worker = select_best_worker(candidates)
            if not worker:
                # No worker available; put the item back at the front of the queue and back off.
                log.warning(
                    "Backfill: no eligible worker for job %s date %s; requeuing",
                    job_id, execution_date,
                )
                r.lpush(f"backfill_queue:{domain}", raw)
                time.sleep(2)
                continue

            wid = worker["worker_id"]
            dispatched_job = _resolve_credential_refs(job, db)
            enqueued_ts = time.time()
            envelope = {
                "job_id": job_id,
                "domain": domain,
                "job": _json_ready(dispatched_job),
                "enqueued_ts": enqueued_ts,
                "dispatch_ts": time.time(),
                "enqueue_reason": "backfill",
                "retry_attempt": 0,
                "params": {
                    "HYDRA_EXECUTION_DATE": execution_date,
                    "HYDRA_IS_BACKFILL": "true",
                },
            }
            r.rpush(f"job_queue:{domain}:{wid}", json.dumps(envelope))
            append_worker_op(
                domain=domain,
                worker_id=wid,
                op_type="dispatch",
                message=f"Backfill job {job_id} dispatched (date={execution_date})",
                details={
                    "job_id": job_id,
                    "execution_date": execution_date,
                    "enqueue_reason": "backfill",
                    "bypass_concurrency": bypass_concurrency,
                },
            )
            event_bus.publish(
                "job_dispatched",
                {
                    "job_id": job_id,
                    "worker_id": wid,
                    "domain": domain,
                    "bypass_concurrency": bypass_concurrency,
                    "execution_date": execution_date,
                    "enqueue_reason": "backfill",
                },
            )
            log.info(
                "Dispatched backfill job %s (date=%s) to worker %s",
                job_id, execution_date, wid,
            )
        except Exception as e:
            log.exception("Error in backfill dispatch loop: %s", e)
            time.sleep(1)


def _activate_sensor(r, job: dict, domain: str, enqueued_ts: float, enqueue_reason: str | None):
    """Move a sensor job into the active_sensors set and emit a run_start event."""
    job_id = job["_id"]
    run_id = uuid.uuid4().hex
    now = time.time()
    executor = job.get("executor") or {}
    r.hset(
        f"sensor_run:{domain}:{run_id}",
        mapping={
            "job_id": job_id,
            "run_id": run_id,
            "domain": domain,
            "user": job.get("user", ""),
            "start_ts": now,
            "last_check_ts": "0",
            "executor": json.dumps(executor),
            "timeout_seconds": str(int(executor.get("timeout_seconds", 3600))),
            "poll_interval_seconds": str(int(executor.get("poll_interval_seconds", 30))),
            "enqueue_reason": enqueue_reason or "",
        },
    )
    r.expire(f"sensor_run:{domain}:{run_id}", 7 * 24 * 3600)
    r.sadd(f"active_sensors:{domain}", run_id)
    # Emit run_start so a run document is created in Mongo
    r.rpush(
        f"run_events:{domain}",
        json.dumps({
            "type": "run_start",
            "run_id": run_id,
            "job_id": job_id,
            "user": job.get("user", ""),
            "domain": domain,
            "worker_id": None,
            "start_ts": now,
            "scheduled_ts": enqueued_ts,
            "executor_type": "sensor",
        }),
    )


def _perform_http_sensor_check(executor: dict, db, domain: str) -> bool:
    """Execute an HTTP sensor check. Returns True if the check succeeds."""
    url = executor.get("target", "")
    method = executor.get("method", "GET").upper()
    headers = dict(executor.get("headers") or {})
    body = executor.get("body")
    expected_status = executor.get("expected_status") or [200]
    request_timeout = min(int(executor.get("poll_interval_seconds", 30)), _HTTP_REQUEST_MAX_TIMEOUT_SECONDS)

    # Resolve credential_ref → Authorization header
    credential_ref = (executor.get("credential_ref") or "").strip()
    if credential_ref:
        cred_doc = db.credentials.find_one({"name": credential_ref, "domain": domain})
        if cred_doc:
            try:
                decrypted = decrypt_payload(cred_doc["encrypted_payload"])
                if decrypted.get("token"):
                    headers["Authorization"] = f"Bearer {decrypted['token']}"
                elif decrypted.get("api_key"):
                    headers["X-API-Key"] = decrypted["api_key"]
                elif decrypted.get("username") and decrypted.get("password"):
                    import base64
                    creds = base64.b64encode(
                        f"{decrypted['username']}:{decrypted['password']}".encode()
                    ).decode()
                    headers["Authorization"] = f"Basic {creds}"
            except Exception:
                log.exception("Failed to decrypt sensor credential '%s'", credential_ref)

    encoded_body = body.encode() if body else None
    req = urllib.request.Request(url, data=encoded_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            return resp.status in expected_status
    except urllib.error.HTTPError as exc:
        return exc.code in expected_status
    except Exception as exc:
        log.debug("HTTP sensor check failed for %s: %s", url, exc)
        return False


def _perform_sql_sensor_check(executor: dict, db, domain: str) -> bool:
    """Execute a SQL sensor check. Returns True if the query returns at least one row."""
    try:
        import sqlalchemy
    except ImportError:
        log.error("sqlalchemy is not installed; cannot perform SQL sensor check")
        return False

    connection_uri = (executor.get("connection_uri") or "").strip()
    credential_ref = (executor.get("credential_ref") or "").strip()
    if not connection_uri and credential_ref:
        cred_doc = db.credentials.find_one({"name": credential_ref, "domain": domain})
        if cred_doc:
            try:
                decrypted = decrypt_payload(cred_doc["encrypted_payload"])
                connection_uri = decrypted.get("connection_uri") or ""
                if not connection_uri and decrypted.get("host"):
                    dialect = executor.get("dialect", "postgres")
                    user = decrypted.get("username", "")
                    password = decrypted.get("password", "")
                    host = decrypted.get("host", "localhost")
                    port = decrypted.get("port", "")
                    database = decrypted.get("database", "")
                    auth = f"{user}:{password}@" if user else ""
                    port_part = f":{port}" if port else ""
                    db_part = f"/{database}" if database else ""
                    scheme = _SQL_DIALECT_MAP.get(dialect, dialect)
                    connection_uri = f"{scheme}://{auth}{host}{port_part}{db_part}"
            except Exception:
                log.exception("Failed to decrypt SQL sensor credential '%s'", credential_ref)

    if not connection_uri:
        log.warning("SQL sensor has no connection_uri; marking check as failed")
        return False

    query = (executor.get("target") or "").strip()
    if not query:
        log.warning("SQL sensor has empty query (target); marking check as failed")
        return False

    try:
        engine = sqlalchemy.create_engine(connection_uri, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(sqlalchemy.text(query))
            row = result.fetchone()
            return row is not None
    except Exception as exc:
        log.debug("SQL sensor check failed: %s", exc)
        return False


def _emit_sensor_run_end(r, domain: str, run_id: str, job_id: str, user: str, status: str, reason: str, start_ts: float):
    """Push a run_end event for a completed/failed sensor run."""
    now = time.time()
    r.rpush(
        f"run_events:{domain}",
        json.dumps({
            "type": "run_end",
            "run_id": run_id,
            "job_id": job_id,
            "user": user,
            "domain": domain,
            "worker_id": None,
            "status": status,
            "end_ts": now,
            "start_ts": start_ts,
            "returncode": 0 if status == "success" else 1,
            "stdout": "",
            "stderr": reason if status == "failed" else "",
            "executor_type": "sensor",
            "completion_reason": reason,
        }),
    )


def sensor_evaluation_loop(stop_event: threading.Event):
    """Evaluate active sensor runs and emit completion events when conditions are met.

    Sensor jobs are routed here by the scheduling loop instead of being
    dispatched to workers.  For each active sensor run the loop:

    1. Checks whether ``poll_interval_seconds`` have elapsed since the last poll.
    2. If so, performs the lightweight check (HTTP status or SQL row-count).
    3. On success emits a ``run_end`` (success) event so downstream dependencies
       trigger as normal.
    4. On timeout emits a ``run_end`` (failed/timeout) event.
    5. On a failed check (condition not yet met) simply updates the last-checked
       timestamp and waits for the next interval.
    """
    db = get_db()
    log.info("Sensor evaluation loop started")
    while not stop_event.is_set():
        try:
            r = get_redis()
            domains = list(r.smembers("hydra:domains") or []) or ["prod"]
            for domain in domains:
                run_ids = r.smembers(f"active_sensors:{domain}") or set()
                for run_id in list(run_ids):
                    try:
                        state = r.hgetall(f"sensor_run:{domain}:{run_id}") or {}
                        if not state:
                            r.srem(f"active_sensors:{domain}", run_id)
                            continue
                        job_id = state.get("job_id", "")
                        user = state.get("user", "")
                        start_ts = float(state.get("start_ts", 0))
                        last_check_ts = float(state.get("last_check_ts", 0))
                        timeout_seconds = int(state.get("timeout_seconds", 3600))
                        poll_interval = int(state.get("poll_interval_seconds", 30))
                        executor_json = state.get("executor", "{}")
                        executor = json.loads(executor_json)
                        now = time.time()

                        # Check for overall timeout
                        if timeout_seconds > 0 and (now - start_ts) >= timeout_seconds:
                            log.warning(
                                "Sensor run %s (job %s) timed out after %.1fs",
                                run_id, job_id, now - start_ts,
                            )
                            _emit_sensor_run_end(r, domain, run_id, job_id, user, "failed", "timeout", start_ts)
                            r.srem(f"active_sensors:{domain}", run_id)
                            r.delete(f"sensor_run:{domain}:{run_id}")
                            continue

                        # Check whether it's time to poll
                        if (now - last_check_ts) < poll_interval:
                            continue

                        # Perform the sensor check
                        sensor_type = executor.get("sensor_type", "http")
                        try:
                            if sensor_type == "http":
                                succeeded = _perform_http_sensor_check(executor, db, domain)
                            elif sensor_type == "sql":
                                succeeded = _perform_sql_sensor_check(executor, db, domain)
                            else:
                                log.warning("Unknown sensor_type '%s' for run %s; skipping", sensor_type, run_id)
                                r.hset(f"sensor_run:{domain}:{run_id}", "last_check_ts", str(now))
                                continue
                        except Exception:
                            log.exception("Error performing sensor check for run %s", run_id)
                            r.hset(f"sensor_run:{domain}:{run_id}", "last_check_ts", str(now))
                            continue

                        if succeeded:
                            log.info("Sensor run %s (job %s) condition met; marking success", run_id, job_id)
                            _emit_sensor_run_end(r, domain, run_id, job_id, user, "success", "condition_met", start_ts)
                            r.srem(f"active_sensors:{domain}", run_id)
                            r.delete(f"sensor_run:{domain}:{run_id}")
                        else:
                            log.debug(
                                "Sensor run %s (job %s) condition not yet met; next check in %ss",
                                run_id, job_id, poll_interval,
                            )
                            r.hset(f"sensor_run:{domain}:{run_id}", "last_check_ts", str(now))
                    except Exception:
                        log.exception("Error evaluating sensor run %s in domain %s", run_id, domain)
        except Exception as exc:
            log.exception("Error in sensor evaluation loop: %s", exc)
        time.sleep(_SENSOR_LOOP_SLEEP_SECONDS)
