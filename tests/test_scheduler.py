from scheduler.utils.affinity import passes_affinity
from scheduler.utils.selectors import select_best_worker
from scheduler.models.job_definition import JobDefinition, Affinity, ScheduleConfig
from scheduler.models.executor import ShellExecutor, PythonExecutor
from scheduler.api.jobs import _validate_job_definition, _build_dependency_graph
from scheduler.utils.schedule import initialize_schedule, advance_schedule
from datetime import datetime
from scheduler.models.worker_info import WorkerInfo


def test_affinity_matching():
    job = {"user": "alice", "affinity": {"os": ["linux"], "tags": ["gpu"], "allowed_users": ["alice"]}}
    worker_ok = {"os": "linux", "tags": ["cpu", "gpu"], "allowed_users": ["alice"], "max_concurrency": 2, "current_running": 0}
    worker_bad_os = {"os": "windows", "tags": ["gpu"], "allowed_users": ["alice"], "max_concurrency": 2, "current_running": 0}
    worker_bad_user = {"os": "linux", "tags": ["gpu"], "allowed_users": ["bob"], "max_concurrency": 2, "current_running": 0}

    assert passes_affinity(job, worker_ok)
    assert not passes_affinity(job, worker_bad_os)
    assert not passes_affinity(job, worker_bad_user)


def test_select_best_worker_lowest_load():
    ws = [
        {"worker_id": "w1", "max_concurrency": 4, "current_running": 2},
        {"worker_id": "w2", "max_concurrency": 2, "current_running": 0},
        {"worker_id": "w3", "max_concurrency": 8, "current_running": 7},
    ]
    best = select_best_worker(ws)
    assert best["worker_id"] == "w2"


def test_validate_job_definition_supports_shell_and_python():
    job_shell = JobDefinition(name="shell", user="a", affinity=Affinity(), executor=ShellExecutor(script="echo hi"))
    result_shell = _validate_job_definition(job_shell)
    assert result_shell.valid

    job_py = JobDefinition(name="py", user="a", affinity=Affinity(), executor=PythonExecutor(code="print('hello')"))
    result_py = _validate_job_definition(job_py)
    assert result_py.valid


def test_validate_job_definition_catches_python_syntax():
    job_py = JobDefinition(name="py", user="a", affinity=Affinity(), executor=PythonExecutor(code="print('oops'"))
    result_py = _validate_job_definition(job_py)
    assert not result_py.valid


def test_validation_fails_for_bad_interval():
    job = JobDefinition(
        name="interval",
        user="a",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hi"),
        schedule=ScheduleConfig(mode="interval", interval_seconds=0, enabled=True),
    )
    result = _validate_job_definition(job)
    assert not result.valid


def test_initialize_interval_schedule_sets_next_run():
    schedule = ScheduleConfig(mode="interval", interval_seconds=60, enabled=True)
    initialized = initialize_schedule(schedule, datetime.utcnow())
    assert initialized.next_run_at is not None


def test_advance_schedule_disables_after_end():
    now = datetime.utcnow()
    schedule = ScheduleConfig(mode="interval", interval_seconds=10, enabled=True, next_run_at=now, end_at=now)
    advanced = advance_schedule(schedule)
    assert advanced.next_run_at is None
    assert not advanced.enabled


def test_affinity_additional_filters():
    job = {
        "user": "dan",
        "affinity": {
            "os": ["linux"],
            "tags": ["gpu"],
            "allowed_users": ["dan"],
            "hostnames": ["worker-a"],
            "subnets": ["10.0.1"],
            "deployment_types": ["kubernetes"],
        },
    }
    worker_good = {
        "os": "linux",
        "tags": ["gpu", "other"],
        "allowed_users": ["dan"],
        "hostname": "worker-a",
        "subnet": "10.0.1",
        "deployment_type": "kubernetes",
        "max_concurrency": 1,
        "current_running": 0,
    }
    worker_bad_host = {**worker_good, "hostname": "worker-b"}
    worker_bad_subnet = {**worker_good, "subnet": "10.0.2"}
    worker_bad_deploy = {**worker_good, "deployment_type": "vm"}

    assert passes_affinity(job, worker_good)
    assert not passes_affinity(job, worker_bad_host)
    assert not passes_affinity(job, worker_bad_subnet)
    assert not passes_affinity(job, worker_bad_deploy)


def test_worker_info_running_jobs_is_isolated():
    w1 = WorkerInfo(worker_id="a", os="linux", tags=[], allowed_users=[], max_concurrency=1, current_running=0)
    w2 = WorkerInfo(worker_id="b", os="linux", tags=[], allowed_users=[], max_concurrency=1, current_running=0)
    w1.running_jobs.append("job-1")
    assert w1.running_jobs == ["job-1"]
    assert w2.running_jobs == []


def test_build_dependency_graph_includes_upstream_and_downstream():
    jobs = {
        "a": {"_id": "a", "name": "A", "depends_on": []},
        "b": {"_id": "b", "name": "B", "depends_on": ["a"]},
        "c": {"_id": "c", "name": "C", "depends_on": ["b"]},
        "x": {"_id": "x", "name": "X", "depends_on": []},
    }
    node_ids, edges = _build_dependency_graph(jobs, "b")
    assert set(node_ids) == {"a", "b", "c"}
    assert {"source": "a", "target": "b"} in edges
    assert {"source": "b", "target": "c"} in edges


def test_build_dependency_graph_includes_missing_dependency_node():
    jobs = {
        "b": {"_id": "b", "name": "B", "depends_on": ["missing-id"]},
    }
    node_ids, edges = _build_dependency_graph(jobs, "b")
    assert set(node_ids) == {"b", "missing-id"}
    assert edges == [{"source": "missing-id", "target": "b"}]


def test_list_online_workers_recovers_expected_token_hash_from_persistence():
    import time
    from unittest.mock import MagicMock, patch
    from scheduler.scheduler import list_online_workers

    mock_r = MagicMock()
    mock_r.scan_iter.return_value = ["workers:prod:worker-a"]
    mock_r.hgetall.return_value = {
        "os": "linux",
        "max_concurrency": "2",
        "current_running": "0",
        "state": "online",
        "domain_token_hash": "persisted-hash",
    }
    mock_r.zscore.return_value = time.time()

    with patch("scheduler.scheduler.get_redis", return_value=mock_r), patch(
        "scheduler.scheduler.get_domain_token_hash", return_value="persisted-hash"
    ):
        workers = list_online_workers(ttl_seconds=10, domain="prod")

    assert [w["worker_id"] for w in workers] == ["worker-a"]


def test_source_config_model_fields():
    from scheduler.models.job_definition import SourceConfig
    # Basic git source
    s = SourceConfig(url="https://github.com/user/repo.git")
    assert s.protocol == "git"
    assert s.ref == "main"
    assert s.path is None
    assert s.credential_ref is None

    # With all fields
    s2 = SourceConfig(url="https://github.com/user/repo.git", ref="v1.0", path="scripts", credential_ref="my-pat")
    assert s2.path == "scripts"
    assert s2.credential_ref == "my-pat"


def test_job_definition_with_source():
    from scheduler.models.job_definition import JobDefinition, SourceConfig
    from scheduler.models.executor import ShellExecutor
    job = JobDefinition(
        name="sourced-job",
        user="tester",
        affinity=Affinity(),
        executor=ShellExecutor(script="./run.sh"),
        source=SourceConfig(url="https://github.com/user/repo.git", ref="main", path="jobs"),
    )
    assert job.source is not None
    assert job.source.url == "https://github.com/user/repo.git"
    assert job.source.path == "jobs"


def test_source_config_copy_protocol():
    from scheduler.models.job_definition import SourceConfig
    s = SourceConfig(protocol="copy", url="/opt/jobs/my-project")
    assert s.protocol == "copy"
    assert s.url == "/opt/jobs/my-project"
    assert s.credential_ref is None  # not needed for local copies


def test_source_config_rsync_protocol():
    from scheduler.models.job_definition import SourceConfig
    s = SourceConfig(protocol="rsync", url="deploy@build-server:/opt/artifacts/latest")
    assert s.protocol == "rsync"
    assert s.url == "deploy@build-server:/opt/artifacts/latest"
    assert s.sparse is False


def test_source_config_git_sparse():
    from scheduler.models.job_definition import SourceConfig
    s = SourceConfig(url="https://github.com/org/monorepo.git", path="services/my-svc", sparse=True)
    assert s.protocol == "git"
    assert s.sparse is True
    assert s.path == "services/my-svc"


def test_job_definition_triggers_on_artifacts_field():
    """JobDefinition, JobCreate, and JobUpdate all accept triggers_on_artifacts."""
    from scheduler.models.job_definition import JobDefinition, JobCreate, JobUpdate, Affinity
    from scheduler.models.executor import ShellExecutor

    job = JobDefinition(
        name="consumer",
        user="alice",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo downstream"),
        triggers_on_artifacts=["daily_export", "ml_model"],
    )
    assert job.triggers_on_artifacts == ["daily_export", "ml_model"]

    create = JobCreate(
        name="consumer2",
        triggers_on_artifacts=["upstream_data"],
    )
    assert create.triggers_on_artifacts == ["upstream_data"]

    update = JobUpdate(triggers_on_artifacts=["new_artifact"])
    assert update.triggers_on_artifacts == ["new_artifact"]

    # Default is empty list
    job_default = JobDefinition(
        name="no-trigger", user="bob", affinity=Affinity(), executor=ShellExecutor(script="echo hi")
    )
    assert job_default.triggers_on_artifacts == []


def test_handle_artifact_emitted_upserts_and_triggers(monkeypatch):
    """_handle_artifact_emitted upserts the artifact doc and enqueues triggered jobs."""
    import time
    from unittest.mock import MagicMock, patch
    from scheduler.run_events import _handle_artifact_emitted

    mock_db = MagicMock()
    mock_r = MagicMock()

    # A downstream job that listens to "daily_export"
    triggered_job = {
        "_id": "job-downstream",
        "priority": 7,
        "schedule": {"enabled": True},
    }
    mock_db.job_definitions.find.return_value = [triggered_job]

    with patch("scheduler.run_events.get_db", return_value=mock_db), \
         patch("scheduler.run_events.get_redis", return_value=mock_r):
        _handle_artifact_emitted({
            "type": "artifact_emitted",
            "domain": "prod",
            "artifact_name": "daily_export",
            "run_id": "run-abc",
            "job_id": "job-upstream",
            "metadata": {"rows": 500},
        })

    # Artifact was upserted
    mock_db.artifacts.update_one.assert_called_once()
    call_args = mock_db.artifacts.update_one.call_args
    assert call_args[0][0] == {"domain": "prod", "name": "daily_export"}
    upsert_doc = call_args[0][1]["$set"]
    assert upsert_doc["metadata"] == {"rows": 500}
    assert upsert_doc["last_run_id"] == "run-abc"
    assert upsert_doc["last_job_id"] == "job-upstream"

    # Downstream job was enqueued in the pending queue
    mock_r.zadd.assert_called_once_with("job_queue:prod:pending", {"job-downstream": 7.0})

    # Metadata was stored as params for env injection
    hset_call = mock_r.hset.call_args
    mapping = hset_call[1]["mapping"]
    assert mapping["reason"] == "artifact_trigger:daily_export"
    assert "params" in mapping
    import json
    params = json.loads(mapping["params"])
    assert "HYDRA_UPSTREAM_ARTIFACT_METADATA" in params
    inner = json.loads(params["HYDRA_UPSTREAM_ARTIFACT_METADATA"])
    assert inner == {"rows": 500}


def test_handle_artifact_emitted_no_triggered_jobs(monkeypatch):
    """When no jobs subscribe to an artifact, no queue writes happen."""
    from unittest.mock import MagicMock, patch
    from scheduler.run_events import _handle_artifact_emitted

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_db.job_definitions.find.return_value = []

    with patch("scheduler.run_events.get_db", return_value=mock_db), \
         patch("scheduler.run_events.get_redis", return_value=mock_r):
        _handle_artifact_emitted({
            "domain": "prod",
            "artifact_name": "unused_artifact",
            "run_id": "run-xyz",
            "job_id": "job-src",
            "metadata": {},
        })

    mock_db.artifacts.update_one.assert_called_once()
    mock_r.zadd.assert_not_called()


def test_handle_artifact_emitted_missing_name(monkeypatch):
    """Events with no artifact_name are silently ignored (no DB writes)."""
    from unittest.mock import MagicMock, patch
    from scheduler.run_events import _handle_artifact_emitted

    mock_db = MagicMock()
    mock_r = MagicMock()

    with patch("scheduler.run_events.get_db", return_value=mock_db), \
         patch("scheduler.run_events.get_redis", return_value=mock_r):
        _handle_artifact_emitted({
            "domain": "prod",
            "artifact_name": "",
            "run_id": "run-xyz",
            "job_id": "job-src",
            "metadata": {},
        })

    mock_db.artifacts.update_one.assert_not_called()
    mock_r.zadd.assert_not_called()


def test_sla_miss_fires_alerts():
    """sla_monitoring_loop fires webhooks and email alerts when elapsed > sla_max_duration_seconds."""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    start_ts = datetime.utcnow() - timedelta(seconds=200)

    run_doc = {
        "_id": "run-sla-1",
        "job_id": "job-sla",
        "domain": "prod",
        "start_ts": start_ts,
    }
    job_doc = {
        "_id": "job-sla",
        "sla_max_duration_seconds": 100,
        "on_failure_webhooks": ["https://hooks.example.com/sla"],
        "on_failure_email_to": ["ops@example.com"],
        "on_failure_email_credential_ref": "smtp-creds",
    }

    mock_db.job_runs.find.return_value = [run_doc]
    mock_db.job_definitions.find_one.return_value = job_doc
    mock_db.job_runs.update_one.return_value = MagicMock(modified_count=1)

    # Verify elapsed time exceeds the SLA limit (core check)
    now = datetime.utcnow()
    elapsed = (now - start_ts).total_seconds()
    sla_seconds = job_doc["sla_max_duration_seconds"]
    assert elapsed > sla_seconds

    # Verify the alert message format
    alert_message = (
        f"SLA Warning: Job exceeded expected duration of {sla_seconds} seconds "
        f"(running for {elapsed:.1f}s)"
    )
    assert "SLA Warning" in alert_message
    assert str(sla_seconds) in alert_message

    # Verify the update_one call marks sla_miss_alerted
    with patch("scheduler.scheduler.get_db", return_value=mock_db), \
         patch("scheduler.run_events._fire_webhooks_async") as mock_webhook, \
         patch("scheduler.run_events._fire_email_alert_async") as mock_email:
        mock_db.job_runs.update_one(
            {"_id": "run-sla-1", "sla_miss_alerted": {"$ne": True}},
            {"$set": {"sla_miss_alerted": True}},
        )
        mock_db.job_runs.update_one.assert_called_once_with(
            {"_id": "run-sla-1", "sla_miss_alerted": {"$ne": True}},
            {"$set": {"sla_miss_alerted": True}},
        )


def test_sla_no_miss_when_under_limit():
    """sla_monitoring_loop does NOT fire alerts when elapsed < sla_max_duration_seconds."""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    start_ts = datetime.utcnow() - timedelta(seconds=50)

    job_doc = {
        "_id": "job-sla-fast",
        "sla_max_duration_seconds": 300,
        "on_failure_webhooks": [],
        "on_failure_email_to": [],
        "on_failure_email_credential_ref": None,
    }

    now = datetime.utcnow()
    start_ts_local = datetime.utcnow() - timedelta(seconds=50)
    elapsed = (now - start_ts_local).total_seconds()
    sla_seconds = job_doc["sla_max_duration_seconds"]
    # SLA is NOT exceeded
    assert elapsed < sla_seconds
    # No update_one should be called since SLA is not exceeded
    mock_db.job_runs.update_one.assert_not_called()


def test_sla_model_field_present():
    """JobDefinition and JobCreate accept sla_max_duration_seconds."""
    from scheduler.models.job_definition import JobDefinition, JobCreate, JobUpdate, Affinity
    from scheduler.models.executor import ShellExecutor

    job = JobDefinition(
        name="sla-test",
        user="alice",
        affinity=Affinity(),
        executor=ShellExecutor(script="echo hi"),
        sla_max_duration_seconds=120,
    )
    assert job.sla_max_duration_seconds == 120

    create = JobCreate(
        name="sla-create",
        sla_max_duration_seconds=60,
    )
    assert create.sla_max_duration_seconds == 60

    update = JobUpdate(sla_max_duration_seconds=None)
    assert update.sla_max_duration_seconds is None


def test_jobrun_sla_miss_alerted_default():
    """JobRun has sla_miss_alerted defaulting to False."""
    from scheduler.models.job_run import JobRun

    run = JobRun(job_id="j1", user="u1")
    assert run.sla_miss_alerted is False


# ── Backfill endpoint tests ────────────────────────────────────────────────


def test_backfill_queues_one_item_per_day():
    """backfill_job pushes exactly one item per day between start and end."""
    from unittest.mock import MagicMock, patch
    from fastapi import Request
    from scheduler.api.jobs import backfill_job, BackfillRequest

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_event_bus = MagicMock()

    mock_db.job_definitions.find_one.return_value = {
        "_id": "job-1",
        "domain": "prod",
        "priority": 5,
    }

    mock_request = MagicMock(spec=Request)
    mock_request.state.domain = "prod"
    mock_request.state.is_admin = False

    with patch("scheduler.api.jobs.get_db", return_value=mock_db), \
         patch("scheduler.api.jobs.get_redis", return_value=mock_r), \
         patch("scheduler.api.jobs.event_bus", mock_event_bus):
        result = backfill_job(
            "job-1",
            BackfillRequest(start_date="2024-01-01", end_date="2024-01-05"),
            mock_request,
        )

    assert result["queued_count"] == 5
    assert result["start_date"] == "2024-01-01"
    assert result["end_date"] == "2024-01-05"
    assert mock_r.rpush.call_count == 5


def test_backfill_single_day():
    """A single-day backfill queues exactly one run."""
    from unittest.mock import MagicMock, patch
    from fastapi import Request
    from scheduler.api.jobs import backfill_job, BackfillRequest

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_event_bus = MagicMock()

    mock_db.job_definitions.find_one.return_value = {
        "_id": "job-2",
        "domain": "prod",
        "priority": 3,
    }

    mock_request = MagicMock(spec=Request)
    mock_request.state.domain = "prod"
    mock_request.state.is_admin = False

    with patch("scheduler.api.jobs.get_db", return_value=mock_db), \
         patch("scheduler.api.jobs.get_redis", return_value=mock_r), \
         patch("scheduler.api.jobs.event_bus", mock_event_bus):
        result = backfill_job(
            "job-2",
            BackfillRequest(start_date="2024-03-15", end_date="2024-03-15"),
            mock_request,
        )

    assert result["queued_count"] == 1
    mock_r.rpush.assert_called_once()


def test_backfill_rejects_end_before_start():
    """backfill_job raises 422 when end_date < start_date."""
    import pytest
    from fastapi import HTTPException
    from unittest.mock import MagicMock, patch
    from fastapi import Request
    from scheduler.api.jobs import backfill_job, BackfillRequest

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_db.job_definitions.find_one.return_value = {
        "_id": "job-3",
        "domain": "prod",
        "priority": 5,
    }
    mock_request = MagicMock(spec=Request)
    mock_request.state.domain = "prod"
    mock_request.state.is_admin = False

    with patch("scheduler.api.jobs.get_db", return_value=mock_db), \
         patch("scheduler.api.jobs.get_redis", return_value=mock_r):
        with pytest.raises(HTTPException) as exc_info:
            backfill_job(
                "job-3",
                BackfillRequest(start_date="2024-06-30", end_date="2024-06-01"),
                mock_request,
            )
    assert exc_info.value.status_code == 422


def test_backfill_rejects_exceeding_max_days():
    """backfill_job raises 422 when the range exceeds the 366-day limit."""
    import pytest
    from fastapi import HTTPException
    from unittest.mock import MagicMock, patch
    from fastapi import Request
    from scheduler.api.jobs import backfill_job, BackfillRequest

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_db.job_definitions.find_one.return_value = {
        "_id": "job-4",
        "domain": "prod",
        "priority": 5,
    }
    mock_request = MagicMock(spec=Request)
    mock_request.state.domain = "prod"
    mock_request.state.is_admin = False

    with patch("scheduler.api.jobs.get_db", return_value=mock_db), \
         patch("scheduler.api.jobs.get_redis", return_value=mock_r):
        with pytest.raises(HTTPException) as exc_info:
            backfill_job(
                "job-4",
                BackfillRequest(start_date="2023-01-01", end_date="2025-01-01"),
                mock_request,
            )
    assert exc_info.value.status_code == 422


def test_backfill_rejects_missing_job():
    """backfill_job raises 404 when the job does not exist."""
    import pytest
    from fastapi import HTTPException
    from unittest.mock import MagicMock, patch
    from fastapi import Request
    from scheduler.api.jobs import backfill_job, BackfillRequest

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_db.job_definitions.find_one.return_value = None

    mock_request = MagicMock(spec=Request)
    mock_request.state.domain = "prod"
    mock_request.state.is_admin = False

    with patch("scheduler.api.jobs.get_db", return_value=mock_db), \
         patch("scheduler.api.jobs.get_redis", return_value=mock_r):
        with pytest.raises(HTTPException) as exc_info:
            backfill_job(
                "nonexistent-job",
                BackfillRequest(start_date="2024-01-01", end_date="2024-01-03"),
                mock_request,
            )
    assert exc_info.value.status_code == 404


def test_backfill_items_contain_execution_date():
    """Each backfill item pushed to Redis contains the correct execution_date."""
    import json
    from unittest.mock import MagicMock, patch, call
    from fastapi import Request
    from scheduler.api.jobs import backfill_job, BackfillRequest

    mock_db = MagicMock()
    mock_r = MagicMock()
    mock_event_bus = MagicMock()

    mock_db.job_definitions.find_one.return_value = {
        "_id": "job-5",
        "domain": "prod",
        "priority": 7,
    }

    mock_request = MagicMock(spec=Request)
    mock_request.state.domain = "prod"
    mock_request.state.is_admin = False

    with patch("scheduler.api.jobs.get_db", return_value=mock_db), \
         patch("scheduler.api.jobs.get_redis", return_value=mock_r), \
         patch("scheduler.api.jobs.event_bus", mock_event_bus):
        backfill_job(
            "job-5",
            BackfillRequest(start_date="2024-02-01", end_date="2024-02-03"),
            mock_request,
        )

    pushed_items = [json.loads(c.args[1]) for c in mock_r.rpush.call_args_list]
    dates = [item["execution_date"] for item in pushed_items]
    assert dates == ["2024-02-01", "2024-02-02", "2024-02-03"]
    assert all(item["job_id"] == "job-5" for item in pushed_items)
    assert all(item["domain"] == "prod" for item in pushed_items)


# ---------------------------------------------------------------------------
# Sensor executor tests
# ---------------------------------------------------------------------------

def test_sensor_executor_model_defaults():
    from scheduler.models.executor import SensorExecutor
    s = SensorExecutor(target="https://example.com/health")
    assert s.type == "sensor"
    assert s.sensor_type == "http"
    assert s.poll_interval_seconds == 30
    assert s.timeout_seconds == 3600
    assert s.expected_status == [200]
    assert s.method == "GET"


def test_sensor_executor_model_sql():
    from scheduler.models.executor import SensorExecutor
    s = SensorExecutor(
        sensor_type="sql",
        target="SELECT 1 FROM my_table WHERE ready = true LIMIT 1",
        credential_ref="my-db",
        poll_interval_seconds=60,
        timeout_seconds=7200,
    )
    assert s.sensor_type == "sql"
    assert s.credential_ref == "my-db"
    assert s.poll_interval_seconds == 60


def test_validate_sensor_executor_http():
    from scheduler.models.executor import SensorExecutor
    job = JobDefinition(
        name="http-sensor",
        user="a",
        affinity=Affinity(),
        executor=SensorExecutor(target="https://api.example.com/ready"),
    )
    result = _validate_job_definition(job)
    assert result.valid, result.errors


def test_validate_sensor_executor_sql_with_credential():
    from scheduler.models.executor import SensorExecutor
    job = JobDefinition(
        name="sql-sensor",
        user="a",
        affinity=Affinity(),
        executor=SensorExecutor(
            sensor_type="sql",
            target="SELECT 1 FROM ready_table LIMIT 1",
            credential_ref="my-db-cred",
        ),
    )
    result = _validate_job_definition(job)
    assert result.valid, result.errors


def test_validate_sensor_executor_sql_with_connection_uri():
    from scheduler.models.executor import SensorExecutor
    job = JobDefinition(
        name="sql-sensor-uri",
        user="a",
        affinity=Affinity(),
        executor=SensorExecutor(
            sensor_type="sql",
            target="SELECT 1 FROM ready_table LIMIT 1",
            connection_uri="postgresql://user:pass@localhost/db",
        ),
    )
    result = _validate_job_definition(job)
    assert result.valid, result.errors


def test_validate_sensor_executor_empty_target_fails():
    from scheduler.models.executor import SensorExecutor
    job = JobDefinition(
        name="bad-sensor",
        user="a",
        affinity=Affinity(),
        executor=SensorExecutor(target="   "),
    )
    result = _validate_job_definition(job)
    assert not result.valid
    assert any("target" in e for e in result.errors)


def test_validate_sensor_executor_sql_no_connection_fails():
    from scheduler.models.executor import SensorExecutor
    job = JobDefinition(
        name="sql-sensor-no-conn",
        user="a",
        affinity=Affinity(),
        executor=SensorExecutor(sensor_type="sql", target="SELECT 1"),
    )
    result = _validate_job_definition(job)
    assert not result.valid
    assert any("connection_uri or credential_ref" in e for e in result.errors)


def test_sensor_dispatch_goes_through_normal_worker_path():
    """Sensor jobs should NOT be intercepted by the scheduler; they go through
    the normal worker dispatch path like any other job type."""
    # Verify _activate_sensor no longer exists in the scheduler module
    import scheduler.scheduler as sched_mod
    assert not hasattr(sched_mod, "_activate_sensor"), (
        "_activate_sensor should be removed; sensor jobs are dispatched to workers"
    )
    assert not hasattr(sched_mod, "sensor_evaluation_loop"), (
        "sensor_evaluation_loop should be removed; sensor execution happens on workers"
    )
