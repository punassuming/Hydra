"""Test the new job management improvements"""
from scheduler.models.job_definition import JobDefinition, Affinity
from scheduler.models.executor import ShellExecutor
from scheduler.api.jobs import _validate_job_definition


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
