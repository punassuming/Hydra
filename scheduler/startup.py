"""Shared startup helpers used by both the API server and the standalone orchestrator.

Extracted from main.py so both entrypoints can perform the same initialization
without creating circular imports.
"""

import hashlib
import os
import secrets

from .utils.logging import setup_logging
from .utils.redis_acl import ensure_worker_acl_user
from .redis_client import get_redis
from .mongo_client import get_db

log = setup_logging("scheduler.startup")

DEFAULT_ADMIN_TOKEN = "admin_secret"


def ensure_admin_token() -> None:
    """Ensure ADMIN_TOKEN is set, falling back to a default with a warning."""
    admin_token = os.getenv("ADMIN_TOKEN")
    if not admin_token:
        admin_token = DEFAULT_ADMIN_TOKEN
        os.environ["ADMIN_TOKEN"] = admin_token
        log.warning("ADMIN_TOKEN not set; using default ADMIN_TOKEN. Set ADMIN_TOKEN in production.")
    try:
        from .utils import auth
        auth.ADMIN_TOKEN = admin_token
    except Exception:
        pass


def ensure_domains_seeded() -> None:
    """Cache existing domain token hashes into Redis; seed a default 'prod' domain if none exist."""
    r = get_redis()
    db = get_db()
    for doc in db.domains.find({}):
        domain = doc.get("domain")
        token_hash = doc.get("token_hash")
        if not domain or not token_hash:
            continue
        r.sadd("hydra:domains", domain)
        r.set(f"token_hash:{domain}", token_hash)
        r.set(f"token_hash:{token_hash}:domain", domain)
        acl_password = doc.get("worker_redis_acl_password")
        if acl_password:
            try:
                ensure_worker_acl_user(domain, password=acl_password)
            except Exception as exc:
                log.warning("Failed to restore Redis ACL user for domain %s: %s", domain, exc)
        else:
            log.warning(
                "Domain %s has no persisted worker Redis ACL password; rotate ACL once to enable restart-safe recovery.",
                domain,
            )
    if db.domains.count_documents({}) == 0:
        token = secrets.token_hex(24)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db.domains.insert_one(
            {"domain": "prod", "display_name": "Production", "description": "Production", "token_hash": token_hash}
        )
        r.sadd("hydra:domains", "prod")
        r.set("token_hash:prod", token_hash)
        r.set(f"token_hash:{token_hash}:domain", "prod")
        log.warning("Seeded default prod domain with token: %s", token)
