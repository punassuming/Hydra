"""Tests for domain-scoped security and user permission hardening."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scheduler.models.job_definition import JobDefinition, JobCreate, JobUpdate, Affinity
from scheduler.models.executor import ShellExecutor


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_job_definition_has_user_field():
    """JobDefinition must expose a user field for audit and affinity checks."""
    job = JobDefinition(
        name="test",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hi"),
        user="alice",
    )
    assert job.user == "alice"


def test_job_definition_user_defaults_to_none():
    """JobDefinition.user should default to None when not provided."""
    job = JobDefinition(name="test", affinity=Affinity(), executor=ShellExecutor(script="echo hi"))
    assert job.user is None


def test_job_create_has_user_field():
    job = JobCreate(name="test", affinity=Affinity(), executor=ShellExecutor(script="echo hi"), user="bob")
    assert job.user == "bob"


def test_job_to_mongo_includes_user():
    job = JobDefinition(name="test", affinity=Affinity(), executor=ShellExecutor(script="echo hi"), user="carol")
    doc = job.to_mongo()
    assert doc.get("user") == "carol"


# ---------------------------------------------------------------------------
# update_job – non-admin cannot reassign a job to another domain
# ---------------------------------------------------------------------------

def _make_app_with_state(is_admin: bool, domain: str):
    """Return a minimal FastAPI test app that simulates the auth middleware state."""
    from scheduler.api.jobs import update_job, router as jobs_router

    app = FastAPI()

    @app.middleware("http")
    async def inject_state(request: Request, call_next):
        request.state.domain = domain
        request.state.is_admin = is_admin
        return await call_next(request)

    app.include_router(jobs_router)
    return app


def _make_existing_job(domain: str = "prod") -> dict:
    job = JobDefinition(
        name="my-job",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hi"),
        domain=domain,
    )
    doc = job.to_mongo()
    return doc


@patch("scheduler.api.jobs.get_db")
def test_non_admin_cannot_change_domain(mock_get_db):
    """A non-admin user must not be able to reassign a job to a different domain."""
    existing = _make_existing_job(domain="prod")
    mock_db = MagicMock()
    mock_db.job_definitions.find_one.return_value = dict(existing)
    mock_db.job_definitions.replace_one.return_value = MagicMock()
    mock_get_db.return_value = mock_db

    app = _make_app_with_state(is_admin=False, domain="prod")
    client = TestClient(app, raise_server_exceptions=True)

    job_id = existing["_id"]
    resp = client.put(f"/jobs/{job_id}", json={"domain": "other_domain"})

    # The request should succeed (no error) but the domain must not be changed.
    assert resp.status_code == 200
    saved_doc = mock_db.job_definitions.replace_one.call_args[0][1]
    assert saved_doc.get("domain") == "prod", (
        "Non-admin domain change was not blocked; domain was: " + str(saved_doc.get("domain"))
    )


@patch("scheduler.api.jobs.get_db")
def test_admin_can_change_domain(mock_get_db):
    """An admin must be allowed to reassign a job to a different domain."""
    existing = _make_existing_job(domain="prod")
    mock_db = MagicMock()
    mock_db.job_definitions.find_one.return_value = dict(existing)
    mock_db.job_definitions.replace_one.return_value = MagicMock()
    mock_get_db.return_value = mock_db

    app = _make_app_with_state(is_admin=True, domain="admin")
    client = TestClient(app, raise_server_exceptions=True)

    job_id = existing["_id"]
    resp = client.put(f"/jobs/{job_id}", json={"domain": "staging"})

    assert resp.status_code == 200
    saved_doc = mock_db.job_definitions.replace_one.call_args[0][1]
    assert saved_doc.get("domain") == "staging"


# ---------------------------------------------------------------------------
# list_workers – non-admin cannot bypass domain via ?domain= query param
# ---------------------------------------------------------------------------

@patch("scheduler.api.workers.get_redis")
def test_list_workers_non_admin_ignores_domain_param(mock_get_redis):
    """Non-admin ?domain= query param must be ignored; only their token domain is used."""
    from scheduler.api.workers import router as workers_router

    mock_r = MagicMock()
    mock_r.scan_iter.return_value = iter([])
    mock_get_redis.return_value = mock_r

    app = FastAPI()

    @app.middleware("http")
    async def inject_state(request: Request, call_next):
        request.state.domain = "prod"
        request.state.is_admin = False
        return await call_next(request)

    app.include_router(workers_router)
    client = TestClient(app)

    # Non-admin passes ?domain=other_domain – should be ignored
    client.get("/workers/?domain=other_domain")

    # scan_iter must only have been called for the token's domain ("prod")
    calls = [str(c) for c in mock_r.scan_iter.call_args_list]
    assert all("prod" in c for c in calls), (
        "scan_iter was called with a domain other than 'prod': " + str(calls)
    )
    assert not any("other_domain" in c for c in calls), (
        "Non-admin was able to query other_domain workers: " + str(calls)
    )


@patch("scheduler.api.workers.get_redis")
def test_list_workers_admin_can_use_domain_param(mock_get_redis):
    """Admin must be able to filter workers via ?domain=."""
    from scheduler.api.workers import router as workers_router

    mock_r = MagicMock()
    mock_r.scan_iter.return_value = iter([])
    mock_get_redis.return_value = mock_r

    app = FastAPI()

    @app.middleware("http")
    async def inject_state(request: Request, call_next):
        request.state.domain = "admin"
        request.state.is_admin = True
        return await call_next(request)

    app.include_router(workers_router)
    client = TestClient(app)

    client.get("/workers/?domain=staging")

    calls = [str(c) for c in mock_r.scan_iter.call_args_list]
    assert any("staging" in c for c in calls), (
        "Admin ?domain=staging filter was not applied: " + str(calls)
    )
