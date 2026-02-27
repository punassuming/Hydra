from fastapi import APIRouter, Request, HTTPException
from typing import List, Dict
import secrets
import hashlib
from datetime import datetime
from ..redis_client import get_redis
from ..mongo_client import get_db
from ..examples.templates import TEMPLATES
from ..utils.redis_acl import ensure_worker_acl_user, delete_worker_acl_user, worker_acl_username
from ..models.credentials import CredentialCreate, CredentialReference
from ..utils.encryption import encrypt_payload

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(request: Request):
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403, detail="admin only")


def _credential_domain(request: Request) -> str:
    """Resolve the effective domain for credential operations."""
    domain = getattr(request.state, "domain", "prod")
    force_domain = (request.query_params.get("domain") or "").strip()
    return force_domain or domain


@router.get("/domains")
def list_domains(request: Request) -> Dict[str, List[Dict]]:
    _require_admin(request)
    r = get_redis()
    db = get_db()
    domains = list(r.smembers("hydra:domains") or [])
    meta = {doc["domain"]: doc for doc in db.domains.find({})}
    result = []
    for d in domains:
        jobs_count = db.job_definitions.count_documents({"domain": d})
        runs_count = db.job_runs.count_documents({"domain": d})
        workers_count = len(list(r.scan_iter(f"workers:{d}:*")))
        result.append(
            {
                "domain": d,
                "display_name": meta.get(d, {}).get("display_name", d),
                "description": meta.get(d, {}).get("description", ""),
                "worker_redis_acl_user": worker_acl_username(d),
                "jobs_count": jobs_count,
                "runs_count": runs_count,
                "workers_count": workers_count,
            }
        )
    return {"domains": result}


@router.post("/domains")
def create_domain(payload: Dict, request: Request):
    _require_admin(request)
    domain = (payload.get("domain") or "").strip()
    if not domain:
        raise HTTPException(status_code=400, detail="domain required")
    display = payload.get("display_name") or domain
    desc = payload.get("description") or ""
    token = payload.get("token") or secrets.token_hex(24)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    r = get_redis()
    db = get_db()
    r.sadd("hydra:domains", domain)
    r.set(f"token_hash:{domain}", token_hash)
    r.set(f"token_hash:{token_hash}:domain", domain)
    db.domains.update_one(
        {"domain": domain},
        {"$set": {"display_name": display, "description": desc, "token_hash": token_hash}},
        upsert=True,
    )
    redis_acl = ensure_worker_acl_user(domain)
    return {"ok": True, "domain": domain, "token": token, "worker_redis_acl": redis_acl}


@router.put("/domains/{domain}")
def rename_domain(domain: str, payload: Dict, request: Request):
    """
    Lightweight rename updates display metadata only (does not move data).
    """
    _require_admin(request)
    display = payload.get("display_name") or domain
    desc = payload.get("description") or ""
    token = payload.get("token")
    token_hash = hashlib.sha256(token.encode()).hexdigest() if token else None
    db = get_db()
    update = {"display_name": display, "description": desc}
    if token_hash:
        update["token_hash"] = token_hash
    db.domains.update_one({"domain": domain}, {"$set": update}, upsert=True)
    if token_hash:
        r = get_redis()
        r.set(f"token_hash:{domain}", token_hash)
        r.set(f"token_hash:{token_hash}:domain", domain)
    return {"ok": True, "domain": domain, "token": token if token else None}


@router.post("/domains/{domain}/token")
def rotate_token(domain: str, request: Request):
    _require_admin(request)
    db = get_db()
    r = get_redis()
    doc = db.domains.find_one({"domain": domain})
    if not doc:
        raise HTTPException(status_code=404, detail="domain not found")
    token = secrets.token_hex(24)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.domains.update_one({"domain": domain}, {"$set": {"token_hash": token_hash}})
    r.set(f"token_hash:{domain}", token_hash)
    r.set(f"token_hash:{token_hash}:domain", domain)
    return {"ok": True, "domain": domain, "token": token}


@router.delete("/domains/{domain}")
def delete_domain(domain: str, request: Request):
    _require_admin(request)
    db = get_db()
    r = get_redis()
    db.domains.delete_one({"domain": domain})
    r.srem("hydra:domains", domain)
    # clear token cache
    token_hash = r.get(f"token_hash:{domain}")
    if token_hash:
        r.delete(f"token_hash:{token_hash}:domain")
    r.delete(f"token_hash:{domain}")
    delete_worker_acl_user(domain)
    return {"ok": True}


@router.post("/domains/{domain}/redis_acl/rotate")
def rotate_worker_redis_acl(domain: str, request: Request):
    _require_admin(request)
    db = get_db()
    doc = db.domains.find_one({"domain": domain})
    if not doc:
        raise HTTPException(status_code=404, detail="domain not found")
    redis_acl = ensure_worker_acl_user(domain)
    return {"ok": True, "domain": domain, "worker_redis_acl": redis_acl}


@router.get("/job_templates")
def list_job_templates(request: Request):
    _require_admin(request)
    return {"templates": TEMPLATES}


@router.post("/job_templates/{template_id}/import")
def import_template(template_id: str, request: Request):
    _require_admin(request)
    db = get_db()
    template = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    # attach domain from request
    domain = getattr(request.state, "domain", "prod")
    job_doc = dict(template)
    job_doc["domain"] = domain
    # ensure unique id
    existing = db.job_definitions.find_one({"name": job_doc["name"], "domain": domain})
    if existing:
        raise HTTPException(status_code=409, detail="job with that name already exists in this domain")
    db.job_definitions.insert_one(job_doc)
    return {"ok": True, "job": job_doc}


# --- Credential Management ---


@router.get("/credentials")
def list_credentials(request: Request) -> Dict:
    _require_admin(request)
    db = get_db()
    force_domain = (request.query_params.get("domain") or "").strip()
    query = {"domain": force_domain} if force_domain else {}
    docs = list(db.credentials.find(query))
    refs = []
    for doc in docs:
        refs.append(CredentialReference(
            name=doc.get("name", ""),
            domain=doc.get("domain", "prod"),
            credential_type=doc.get("credential_type", "database"),
            dialect=doc.get("dialect"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        ).model_dump())
    return {"credentials": refs}


@router.post("/credentials")
def create_credential(payload: CredentialCreate, request: Request):
    _require_admin(request)
    cred_domain = _credential_domain(request)
    db = get_db()
    existing = db.credentials.find_one({"name": payload.name, "domain": cred_domain})
    if existing:
        raise HTTPException(status_code=409, detail="credential with that name already exists in this domain")
    sensitive = payload.model_dump(exclude={"name", "credential_type", "dialect"})
    encrypted = encrypt_payload(sensitive)
    now = datetime.utcnow().isoformat()
    doc = {
        "_id": f"{cred_domain}:{payload.name}",
        "name": payload.name,
        "domain": cred_domain,
        "credential_type": payload.credential_type,
        "dialect": payload.dialect,
        "encrypted_payload": encrypted,
        "created_at": now,
        "updated_at": now,
    }
    db.credentials.insert_one(doc)
    return {"ok": True, "name": payload.name, "domain": cred_domain}


@router.put("/credentials/{name}")
def update_credential(name: str, payload: CredentialCreate, request: Request):
    _require_admin(request)
    cred_domain = _credential_domain(request)
    db = get_db()
    existing = db.credentials.find_one({"name": name, "domain": cred_domain})
    if not existing:
        raise HTTPException(status_code=404, detail="credential not found")
    sensitive = payload.model_dump(exclude={"name", "credential_type", "dialect"})
    encrypted = encrypt_payload(sensitive)
    now = datetime.utcnow().isoformat()
    db.credentials.update_one(
        {"name": name, "domain": cred_domain},
        {"$set": {
            "credential_type": payload.credential_type,
            "dialect": payload.dialect,
            "encrypted_payload": encrypted,
            "updated_at": now,
        }},
    )
    return {"ok": True, "name": name, "domain": cred_domain}


@router.delete("/credentials/{name}")
def delete_credential(name: str, request: Request):
    _require_admin(request)
    cred_domain = _credential_domain(request)
    db = get_db()
    result = db.credentials.delete_one({"name": name, "domain": cred_domain})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="credential not found")
    return {"ok": True}
