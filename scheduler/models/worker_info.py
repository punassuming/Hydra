from typing import List, Optional
from pydantic import BaseModel, Field


class WorkerInfo(BaseModel):
    worker_id: str
    domain: str = "prod"
    os: str
    tags: List[str]
    allowed_users: List[str]
    max_concurrency: int
    current_running: int
    last_heartbeat: Optional[float] = None
    status: str = "online"
    state: str = "online"
    cpu_count: Optional[int] = None
    python_version: Optional[str] = None
    cwd: Optional[str] = None
    hostname: Optional[str] = None
    ip: Optional[str] = None
    subnet: Optional[str] = None
    deployment_type: Optional[str] = None
    run_user: Optional[str] = None
    process_count: Optional[int] = None
    memory_rss_mb: Optional[float] = None
    process_count_max_30m: Optional[int] = None
    memory_rss_mb_max_30m: Optional[float] = None
    metrics_updated_at: Optional[float] = None
    running_jobs: List[str] = Field(default_factory=list)
