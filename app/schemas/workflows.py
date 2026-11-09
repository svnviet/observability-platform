import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_number: int
    attempt_key: str | None
    status: str
    worker_key: str | None
    trace_id: str | None
    trace_url: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    error_details: dict[str, Any] | None


class StepRead(BaseModel):
    id: uuid.UUID
    step_key: str
    step_name: str
    parent_step_id: uuid.UUID | None
    service_name: str | None
    status: str
    latest_attempt_number: int
    sequence_number: int
    started_at: datetime | None
    finished_at: datetime | None
    attempts: list[AttemptRead]


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_key: str
    workflow_id: str
    workflow_name: str | None
    status: str
    correlation_id: str | None
    trace_id: str | None
    trace_url: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    last_event_at: datetime | None
    input_metadata: dict[str, Any]
    output_metadata: dict[str, Any]
    error_details: dict[str, Any] | None


class WorkflowRunDetail(WorkflowRunRead):
    steps: list[StepRead]


class TimelineEntry(BaseModel):
    kind: str  # "workflow" or "step_attempt"
    name: str
    step_id: uuid.UUID | None = None
    attempt_number: int | None = None
    status: str
    service_name: str | None = None
    worker_key: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: str
    workflow_run_id: uuid.UUID
    workflow_step_id: uuid.UUID | None
    attempt_id: uuid.UUID | None
    event_type: str
    event_version: int
    occurred_at: datetime
    received_at: datetime
    source_service: str
    payload: dict[str, Any]
    disposition: str
    disposition_reason: str | None


class ReplayRequest(BaseModel):
    workflow_run_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ReplayRunResult(BaseModel):
    workflow_run_id: uuid.UUID
    found: bool
    events_replayed: int = 0
    applied: int = 0
    stale: int = 0
    quarantined: int = 0


class ReplayResponse(BaseModel):
    results: list[ReplayRunResult]


__all__ = [
    "Page",
    "AttemptRead",
    "StepRead",
    "WorkflowRunRead",
    "WorkflowRunDetail",
    "TimelineEntry",
    "EventRead",
    "ReplayRequest",
    "ReplayRunResult",
    "ReplayResponse",
]
