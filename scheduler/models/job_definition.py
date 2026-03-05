from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator
import uuid
from croniter import croniter

from .executor import ExecutorConfig, ShellExecutor


class Affinity(BaseModel):
    os: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)
    hostnames: List[str] = Field(default_factory=list)
    subnets: List[str] = Field(default_factory=list)
    deployment_types: List[str] = Field(default_factory=list)
    executor_types: List[str] = Field(default_factory=list)


class ScheduleConfig(BaseModel):
    mode: Literal["immediate", "cron", "interval"] = "immediate"
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    timezone: str = "UTC"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule_config(self):
        if self.mode == "cron":
            if not self.cron:
                raise ValueError("cron expression is required when mode='cron'")
            try:
                if not croniter.is_valid(self.cron):
                    raise ValueError("invalid cron syntax")
                # Force parser execution so parser-specific diagnostics surface.
                croniter(self.cron, datetime.utcnow()).get_next(datetime)
            except Exception as exc:
                raise ValueError(f"Invalid cron expression '{self.cron}': {exc}") from exc
        return self


class CompletionCriteria(BaseModel):
    exit_codes: List[int] = Field(default_factory=lambda: [0])
    stdout_contains: List[str] = Field(default_factory=list)
    stdout_not_contains: List[str] = Field(default_factory=list)
    stderr_contains: List[str] = Field(default_factory=list)
    stderr_not_contains: List[str] = Field(default_factory=list)
    require_file_exists: List[str] = Field(default_factory=list)
    require_file_updated_since_start: List[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    protocol: Literal["git", "copy", "rsync"] = "git"
    url: str  # git remote URL for "git"; local path for "copy"; remote host:path for "rsync"
    ref: str = "main"  # git only; ignored for other protocols
    path: Optional[str] = None
    sparse: bool = False  # git only; use sparse-checkout to fetch only 'path' subtree
    credential_ref: Optional[str] = None
    cache: Literal["auto", "always", "never"] = "auto"


class JobDefinition(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, alias="_id")
    name: str
    user: str = "default"
    domain: str = "prod"
    bypass_concurrency: bool = False
    global_locks: List[str] = Field(default_factory=list)
    source: Optional[SourceConfig] = None
    affinity: Affinity
    executor: ExecutorConfig = Field(default_factory=lambda: ShellExecutor(script=""))
    retries: int = 0
    timeout: int = 0
    priority: int = 5
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    completion: CompletionCriteria = Field(default_factory=CompletionCriteria)
    tags: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    max_retries: int = 0
    retry_delay_seconds: int = 0
    on_failure_webhooks: List[str] = Field(default_factory=list)
    on_failure_email_to: List[str] = Field(default_factory=list)
    on_failure_email_credential_ref: Optional[str] = None
    triggers_on_artifacts: List[str] = Field(default_factory=list)
    sla_max_duration_seconds: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True

    def to_mongo(self) -> dict:
        d = self.model_dump(by_alias=True)
        d["created_at"] = self.created_at
        d["updated_at"] = self.updated_at
        return d


class JobCreate(BaseModel):
    name: str
    user: str = "default"
    domain: str = "prod"
    bypass_concurrency: bool = False
    global_locks: List[str] = Field(default_factory=list)
    source: Optional[SourceConfig] = None
    affinity: Affinity = Field(default_factory=Affinity)
    executor: ExecutorConfig = Field(default_factory=lambda: ShellExecutor(script=""))
    retries: int = 0
    timeout: int = 0
    priority: int = 5
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    completion: CompletionCriteria = Field(default_factory=CompletionCriteria)
    tags: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    max_retries: int = 0
    retry_delay_seconds: int = 0
    on_failure_webhooks: List[str] = Field(default_factory=list)
    on_failure_email_to: List[str] = Field(default_factory=list)
    on_failure_email_credential_ref: Optional[str] = None
    triggers_on_artifacts: List[str] = Field(default_factory=list)
    sla_max_duration_seconds: Optional[int] = None


class JobUpdate(BaseModel):
    name: Optional[str] = None
    user: Optional[str] = None
    domain: Optional[str] = None
    bypass_concurrency: Optional[bool] = None
    global_locks: Optional[List[str]] = None
    source: Optional[SourceConfig] = None
    affinity: Optional[Affinity] = None
    executor: Optional[ExecutorConfig] = None
    retries: Optional[int] = None
    timeout: Optional[int] = None
    priority: Optional[int] = None
    schedule: Optional[ScheduleConfig] = None
    completion: Optional[CompletionCriteria] = None
    tags: Optional[List[str]] = None
    depends_on: Optional[List[str]] = None
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[int] = None
    on_failure_webhooks: Optional[List[str]] = None
    on_failure_email_to: Optional[List[str]] = None
    on_failure_email_credential_ref: Optional[str] = None
    triggers_on_artifacts: Optional[List[str]] = None
    sla_max_duration_seconds: Optional[int] = None


class JobValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    next_run_at: Optional[datetime] = None
