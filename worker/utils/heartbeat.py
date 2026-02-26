import threading
import time
import json
import os
from typing import Callable

from ..redis_client import get_redis
from ..config import get_domain


def _collect_process_metrics() -> dict:
    """
    Collect process/memory metrics from the worker container namespace.
    We sum VmRSS across visible /proc entries so child execution processes are included.
    """
    total_rss_kb = 0
    process_count = 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        status_path = f"/proc/{entry}/status"
        try:
            vm_rss_kb = 0
            with open(status_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            vm_rss_kb = int(parts[1])
                        break
            process_count += 1
            total_rss_kb += vm_rss_kb
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError, ValueError):
            # Process exited between listing /proc and opening status; skip safely.
            continue
    return {"process_count": process_count, "memory_rss_mb": round(total_rss_kb / 1024.0, 2)}


def start_heartbeat(worker_id: str, get_active_jobs: Callable[[], list], interval: float = 2.0) -> threading.Thread:
    r = get_redis()
    domain = get_domain()
    sample_interval = max(float(os.getenv("WORKER_METRICS_SAMPLE_SECONDS", "15")), interval)
    window_seconds = max(int(os.getenv("WORKER_METRICS_WINDOW_SECONDS", "1800")), 60)
    max_samples = max(int(window_seconds / sample_interval), 1)

    def _beat():
        last_sample_at = 0.0
        while True:
            now = time.time()
            r.zadd(f"worker_heartbeats:{domain}", {worker_id: now})
            # Keep current_running in sync with active job count for UI accuracy
            active_jobs = get_active_jobs()
            r.hset(f"workers:{domain}:{worker_id}", mapping={"current_running": len(active_jobs)})
            # Update heartbeat for running jobs
            for job_id in active_jobs:
                r.hset(f"job_running:{domain}:{job_id}", mapping={"worker_id": worker_id, "heartbeat": now})

            if now - last_sample_at >= sample_interval:
                try:
                    metrics = _collect_process_metrics()
                    metrics["ts"] = now
                    history_key = f"worker_metrics:{domain}:{worker_id}:history"
                    r.rpush(history_key, json.dumps(metrics))
                    r.ltrim(history_key, -max_samples, -1)
                    r.expire(history_key, max(window_seconds * 2, 3600))
                    r.hset(
                        f"workers:{domain}:{worker_id}",
                        mapping={
                            "process_count": metrics["process_count"],
                            "memory_rss_mb": metrics["memory_rss_mb"],
                            "metrics_ts": now,
                        },
                    )
                except Exception:
                    # Metrics collection should never take down the heartbeat loop.
                    pass
                last_sample_at = now
            time.sleep(interval)

    t = threading.Thread(target=_beat, daemon=True)
    t.start()
    return t
