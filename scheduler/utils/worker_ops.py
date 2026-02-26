import json
import time
from typing import Any

from ..redis_client import get_redis


def append_worker_op(
    domain: str,
    worker_id: str,
    op_type: str,
    message: str,
    details: dict[str, Any] | None = None,
    ts: float | None = None,
):
    r = get_redis()
    event = {
        "ts": ts if ts is not None else time.time(),
        "type": op_type,
        "message": message,
        "details": details or {},
    }
    key = f"worker_ops:{domain}:{worker_id}"
    r.rpush(key, json.dumps(event))
    r.ltrim(key, -1000, -1)
    r.expire(key, 7 * 24 * 3600)
