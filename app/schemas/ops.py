import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.enums import IncidentStatus, JobStatus, Severity


class JobUpsertIn(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    external_job_id: str = Field(min_length=1, max_length=200)
    status: JobStatus
    environment: str = Field(default="unknown", max_length=100)
    instance_id: str | None = Field(default=None, max_length=200)
    worker_name: str | None = Field(default=None, max_length=200)
    workflow_run_key: str | None = Field(default=None, max_length=200)
    trace_id: str | None = Field(default=None, max_length=200)  # lets the job link straight to its trace
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class JobRead(BaseModel):
    id: uuid.UUID
    external_job_id: str
    service_name: str
    worker_id: uuid.UUID | None
    workflow_run_id: uuid.UUID | None
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    metadata: dict[str, Any]
    error_details: dict[str, Any] | None
    trace_id: str | None = None


class JobEventRead(BaseModel):
    id: uuid.UUID
    event_type: str
    previous_status: str | None
    current_status: str
    worker_id: uuid.UUID | None
    occurred_at: datetime
    detail: dict[str, Any]


class JobTimeline(BaseModel):
    job: JobRead
    events: list[JobEventRead]
    queued_s: float | None  # created until first started
    running_s: float | None  # started until finished (or until now while running)
    total_s: float | None


class ObservabilityLink(BaseModel):
    available: bool
    url: str | None = None


class JobObservability(BaseModel):
    job_id: str
    id: uuid.UUID
    service_id: uuid.UUID
    service_name: str
    worker_id: uuid.UUID | None
    worker_name: str | None
    workflow_run_id: uuid.UUID | None
    workflow_id: str | None
    trace_id: str | None
    logs: ObservabilityLink
    trace: ObservabilityLink
    metrics: ObservabilityLink


class IncidentRead(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID | None
    workflow_run_id: uuid.UUID | None
    worker_id: uuid.UUID | None
    severity: Severity
    title: str
    description: str | None
    status: IncidentStatus
    detected_at: datetime
    resolved_at: datetime | None


class WorkflowDefinitionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1", max_length=100)
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinitionRead(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    description: str | None
    definition: dict[str, Any]
    created_at: datetime


class WorkflowRunCreateIn(BaseModel):
    workflow_name: str = Field(min_length=1, max_length=200)
    workflow_id: str = Field(min_length=1, max_length=200)
    run_id: str | None = Field(default=None, max_length=200)
    workflow_version: str = Field(default="1", max_length=100)
    correlation_id: str | None = Field(default=None, max_length=200)
    trace_id: str | None = Field(default=None, max_length=200)
    input_metadata: dict[str, Any] = Field(default_factory=dict)


class RejectedEventRead(BaseModel):
    id: uuid.UUID
    received_at: datetime
    raw: Any
    error: str


class OverviewRead(BaseModel):
    services_total: int
    services_healthy: int
    services_unhealthy: int
    instances_total: int
    workers_total: int
    workers_active: int
    workers_unhealthy: int
    workflows_active: int
    workflows_completed: int
    workflows_failed: int
    jobs_running: int
    jobs_queued: int
    open_incidents: int
    rejected_events: int


class LinksRead(BaseModel):
    jaeger_url: str | None
    perses_url: str | None
    prometheus_url: str | None


class QueueStat(BaseModel):
    service_name: str
    queued: int
    running: int
    completed: int
    failed: int
    oldest_queued_age_s: float | None


class ErrorGroup(BaseModel):
    exception_type: str
    service_name: str | None
    workflow_name: str | None
    count: int
    first_seen: datetime | None
    last_seen: datetime | None
    sample_message: str | None
    sample_workflow_run_id: uuid.UUID | None


class MetricSummary(BaseModel):
    window_hours: int
    workflows_by_status: dict[str, int]
    workflow_duration_avg_ms: float | None
    workflow_duration_p95_ms: float | None
    steps_by_status: dict[str, int]
    attempts_total: int
    retries_total: int  # attempts beyond the first for the same step
    events_received: int
    events_by_disposition: dict[str, int]
