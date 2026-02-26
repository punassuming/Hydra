"""Test the new job management improvements"""
from scheduler.models.job_definition import JobDefinition, Affinity
from scheduler.models.executor import (
    ShellExecutor,
    PowerShellExecutor,
    SqlExecutor,
    ExternalExecutor,
)
from scheduler.api.jobs import _validate_job_definition
from scheduler.utils.affinity import passes_affinity, executor_types_match
from scheduler.utils.encryption import encrypt_payload, decrypt_payload
from worker.executor import _detect_shells, _detect_capabilities


def test_job_definition_with_tags():
    """Test that job definitions can include tags"""
    job = JobDefinition(
        name="test-job",
        user="testuser",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hello"),
        tags=["production", "critical", "data-processing"]
    )
    
    assert job.tags == ["production", "critical", "data-processing"]
    result = _validate_job_definition(job)
    assert result.valid


def test_job_definition_with_empty_tags():
    """Test that job definitions work with empty tags"""
    job = JobDefinition(
        name="test-job",
        user="testuser",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hello"),
        tags=[]
    )
    
    assert job.tags == []
    result = _validate_job_definition(job)
    assert result.valid


def test_job_definition_default_tags():
    """Test that tags default to empty list"""
    job = JobDefinition(
        name="test-job",
        user="testuser",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hello")
    )
    
    assert job.tags == []
    result = _validate_job_definition(job)
    assert result.valid


# --- PowerShell executor tests ---


def test_validate_powershell_executor():
    job = JobDefinition(
        name="ps-job",
        user="a",
        affinity=Affinity(),
        executor=PowerShellExecutor(script="Write-Host 'hello'"),
    )
    result = _validate_job_definition(job)
    assert result.valid


def test_validate_powershell_empty_script_fails():
    job = JobDefinition(
        name="ps-bad",
        user="a",
        affinity=Affinity(),
        executor=PowerShellExecutor(script="  "),
    )
    result = _validate_job_definition(job)
    assert not result.valid
    assert any("powershell" in e for e in result.errors)


# --- SQL executor tests ---


def test_validate_sql_executor():
    job = JobDefinition(
        name="sql-job",
        user="a",
        affinity=Affinity(),
        executor=SqlExecutor(query="SELECT 1;", connection_uri="postgresql://localhost/db"),
    )
    result = _validate_job_definition(job)
    assert result.valid


def test_validate_sql_executor_mongodb():
    job = JobDefinition(
        name="sql-mongo",
        user="a",
        affinity=Affinity(),
        executor=SqlExecutor(dialect="mongodb", query="ping", connection_uri="mongodb://localhost"),
    )
    result = _validate_job_definition(job)
    assert result.valid


def test_validate_sql_no_query_fails():
    job = JobDefinition(
        name="sql-bad",
        user="a",
        affinity=Affinity(),
        executor=SqlExecutor(query="", connection_uri="postgresql://localhost/db"),
    )
    result = _validate_job_definition(job)
    assert not result.valid


def test_validate_sql_no_connection_fails():
    job = JobDefinition(
        name="sql-bad",
        user="a",
        affinity=Affinity(),
        executor=SqlExecutor(query="SELECT 1;"),
    )
    result = _validate_job_definition(job)
    assert not result.valid


def test_validate_sql_credential_ref_is_sufficient():
    job = JobDefinition(
        name="sql-ref",
        user="a",
        affinity=Affinity(),
        executor=SqlExecutor(query="SELECT 1;", credential_ref="my-cred"),
    )
    result = _validate_job_definition(job)
    assert result.valid


# --- Affinity executor_types tests ---


def test_affinity_executor_types_field():
    affinity = Affinity(executor_types=["python", "sql"])
    assert affinity.executor_types == ["python", "sql"]


def test_executor_types_match_empty_passes():
    assert executor_types_match([], ["shell", "python"])


def test_executor_types_match_subset():
    assert executor_types_match(["python"], ["shell", "python", "sql"])


def test_executor_types_match_fails():
    assert not executor_types_match(["powershell"], ["shell", "python"])


def test_passes_affinity_with_executor_types():
    job = {
        "user": "alice",
        "affinity": {
            "os": ["linux"],
            "tags": [],
            "allowed_users": [],
            "executor_types": ["python", "sql"],
        },
    }
    worker_ok = {
        "os": "linux",
        "tags": [],
        "allowed_users": [],
        "capabilities": ["shell", "python", "sql", "external"],
        "max_concurrency": 2,
        "current_running": 0,
    }
    worker_missing_sql = {
        "os": "linux",
        "tags": [],
        "allowed_users": [],
        "capabilities": ["shell", "python"],
        "max_concurrency": 2,
        "current_running": 0,
    }
    assert passes_affinity(job, worker_ok)
    assert not passes_affinity(job, worker_missing_sql)


# --- Worker capability detection ---


def test_detect_shells():
    shells = _detect_shells()
    assert isinstance(shells, list)
    # bash should be detected on Linux CI
    assert "bash" in shells


def test_detect_capabilities():
    caps = _detect_capabilities()
    assert isinstance(caps, list)
    assert "shell" in caps
    assert "external" in caps
    assert "python" in caps


# --- Encryption tests ---


def test_encrypt_decrypt_roundtrip():
    import os
    os.environ["ADMIN_TOKEN"] = "test-admin-token"
    try:
        data = {"connection_uri": "postgresql://user:pass@host/db", "password": "s3cret"}
        token = encrypt_payload(data)
        assert isinstance(token, str)
        decrypted = decrypt_payload(token)
        assert decrypted == data
    finally:
        os.environ.pop("ADMIN_TOKEN", None)


def test_encrypt_produces_different_tokens():
    import os
    os.environ["ADMIN_TOKEN"] = "test-admin-token"
    try:
        data = {"key": "value"}
        t1 = encrypt_payload(data)
        t2 = encrypt_payload(data)
        # Fernet includes timestamp and initialization vector (IV), so tokens differ even for same input
        assert t1 != t2
    finally:
        os.environ.pop("ADMIN_TOKEN", None)
