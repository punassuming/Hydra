"""Tests for new API endpoints added for frontend completeness."""

from datetime import datetime
from scheduler.models.job_definition import (
    JobDefinition,
    JobCreate,
    Affinity,
    ScheduleConfig,
)
from scheduler.models.executor import ShellExecutor


def test_job_definition_with_user_field():
    """Test that JobDefinition now includes user field."""
    job = JobDefinition(
        name="test-job",
        user="testuser",
        affinity=Affinity(os=["linux"]),
        executor=ShellExecutor(script="echo hello"),
    )
    assert job.user == "testuser"
    assert job.name == "test-job"


def test_job_create_with_user_field():
    """Test that JobCreate includes user field."""
    job = JobCreate(
        name="test-job",
        user="testuser",
        affinity=Affinity(os=["linux"]),
        executor=ShellExecutor(script="echo hello"),
    )
    assert job.user == "testuser"


def test_job_create_user_defaults():
    """Test that user defaults to 'default' if not provided."""
    job = JobCreate(
        name="test-job",
        affinity=Affinity(os=["linux"]),
        executor=ShellExecutor(script="echo hello"),
    )
    assert job.user == "default"


def test_pause_resume_schedule_config():
    """Test that ScheduleConfig can be enabled/disabled."""
    schedule = ScheduleConfig(
        mode="interval",
        interval_seconds=300,
        enabled=True
    )
    assert schedule.enabled is True
    
    # Simulate pausing
    schedule.enabled = False
    assert schedule.enabled is False
    
    # Simulate resuming
    schedule.enabled = True
    assert schedule.enabled is True


def test_job_definition_to_mongo_includes_user():
    """Test that user field is included in Mongo export."""
    job = JobDefinition(
        name="test-job",
        user="testuser",
        affinity=Affinity(os=["linux"]),
        executor=ShellExecutor(script="echo hello"),
    )
    mongo_doc = job.to_mongo()
    assert mongo_doc["user"] == "testuser"
    assert "name" in mongo_doc
    assert "affinity" in mongo_doc


def test_bulk_job_creation_payload():
    """Test that multiple jobs can be created with same structure."""
    jobs = [
        JobCreate(
            name=f"test-job-{i}",
            user="bulk-user",
            affinity=Affinity(os=["linux"]),
            executor=ShellExecutor(script=f"echo job {i}"),
        )
        for i in range(3)
    ]
    
    assert len(jobs) == 3
    for i, job in enumerate(jobs):
        assert job.name == f"test-job-{i}"
        assert job.user == "bulk-user"


def test_schedule_modes():
    """Test different schedule modes for pause/resume validation."""
    # Immediate mode (shouldn't be pausable)
    immediate = ScheduleConfig(mode="immediate")
    assert immediate.mode == "immediate"
    
    # Interval mode (should be pausable)
    interval = ScheduleConfig(mode="interval", interval_seconds=300)
    assert interval.mode == "interval"
    assert interval.enabled is True
    
    # Cron mode (should be pausable)
    cron = ScheduleConfig(mode="cron", cron="0 0 * * *")
    assert cron.mode == "cron"
    assert cron.enabled is True
