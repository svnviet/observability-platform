from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.schemas.enums import Disposition, EventType, IngestOutcome

SUPPORTED_EVENT_VERSIONS = frozenset({1})

STEP_EVENT_TYPES = frozenset(
    {
        EventType.STEP_QUEUED,
        EventType.STEP_STARTED,
        EventType.STEP_COMPLETED,
        EventType.STEP_FAILED,
        EventType.STEP_SKIPPED,
        EventType.STEP_CANCELLED,
    }
)


class EventSource(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    instance_id: str | None = Field(default=None, max_length=200)
    worker_id: str | None = Field(default=None, max_length=200)
    environment: str = Field(default="unknown", max_length=100)
    service_version: str | None = Field(default=None, max_length=100)


class EventContext(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=200)
    workflow_run_id: str = Field(min_length=1, max_length=200)
    correlation_id: str | None = Field(default=None, max_length=200)
    trace_id: str | None = Field(default=None, max_length=200)
    step_id: str | None = Field(default=None, max_length=200)
    step_attempt_id: str | None = Field(default=None, max_length=200)


class EventData(BaseModel):
    """Known keys are typed; unknown keys are kept (forward compatibility within a version)."""

    model_config = {"extra": "allow"}

    workflow_name: str | None = Field(default=None, max_length=200)
    workflow_version: str | None = Field(default=None, max_length=100)
    step_name: str | None = Field(default=None, max_length=200)
    parent_step_id: str | None = Field(default=None, max_length=200)
    sequence_number: int | None = Field(default=None, ge=0)
    attempt_number: int = Field(default=1, ge=1)
    will_retry: bool = False  # on STEP_FAILED: the failure is followed by another attempt
    error: dict[str, Any] | None = None
    input_metadata: dict[str, Any] | None = None
    output_metadata: dict[str, Any] | None = None


class EventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    event_type: EventType
    event_version: int = Field(default=1, ge=1)
    occurred_at: AwareDatetime
    source: EventSource
    context: EventContext
    data: EventData = Field(default_factory=EventData)

    @model_validator(mode="after")
    def _step_events_need_step_id(self) -> "EventIn":
        if self.event_type in STEP_EVENT_TYPES and not self.context.step_id:
            raise ValueError(f"{self.event_type} requires context.step_id")
        return self


class EventBatchIn(BaseModel):
    # Raw dicts on purpose: each event is validated individually so one bad event
    # is reported as REJECTED instead of failing the whole batch with a 422.
    events: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class IngestResult(BaseModel):
    event_id: str | None
    outcome: IngestOutcome
    disposition: Disposition | None = None
    detail: str | None = None


class EventBatchResult(BaseModel):
    results: list[IngestResult]
    accepted: int
    duplicates: int
    rejected: int
