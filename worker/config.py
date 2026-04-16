import os
import platform
from typing import List


def get_worker_id() -> str:
    configured = (os.getenv("WORKER_ID") or "").strip()
    if configured:
        return configured
    # Use hostname only (no PID) so the worker re-registers under the same ID
    # after a container restart, preventing ghost "offline" records from
    # accumulating in the UI. Set WORKER_ID explicitly when running multiple
    # workers on the same host.
    return f"worker-{platform.node()}"


def get_tags() -> List[str]:
    tags = os.getenv("WORKER_TAGS", "")
    return [t.strip() for t in tags.split(",") if t.strip()]


def get_allowed_users() -> List[str]:
    v = os.getenv("ALLOWED_USERS", "")
    return [t.strip() for t in v.split(",") if t.strip()]


def get_max_concurrency() -> int:
    try:
        return max(int(os.getenv("MAX_CONCURRENCY", "2")), 1)
    except Exception:
        return 2


def get_initial_state() -> str:
    state = os.getenv("WORKER_STATE", "online").lower()
    return state if state in {"online", "draining", "disabled"} else "online"


def get_domain() -> str:
    return (os.getenv("DOMAIN") or "prod").strip()


def get_domain_token() -> str:
    token = (os.getenv("API_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("API_TOKEN is required for domain-scoped worker registration")
    return token
