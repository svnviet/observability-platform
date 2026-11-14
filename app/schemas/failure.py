import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.ops import IncidentRead


class RootCause(BaseModel):
    source: str  # job, step_attempt or workflow: where the error was recorded
    service_name: str | None
    worker: str | None
    step_name: str | None
    attempt_number: int | None
    error_type: str | None
    message: str | None
    stack_trace: str | None
    location: str | None  # innermost frame found in the stack trace, e.g. app/db.py:42 in connect
    category: str  # DEPENDENCY, TIMEOUT, RESOURCE, AUTH, CRASH, CODE or UNKNOWN (a heuristic)
    category_reason: str | None
    occurred_at: datetime | None


class Precedent(BaseModel):
    at: datetime
    what: str
    detail: str | None = None


class Occurrence(BaseModel):
    count_24h: int
    count_7d: int
    first_seen: datetime | None
    last_seen: datetime | None
    is_new: bool  # no earlier failure with this signature in the last 7 days


class FailureAnalysis(BaseModel):
    kind: str  # job or workflow_run
    id: uuid.UUID
    label: str
    status: str
    failed: bool
    summary: str
    root_cause: RootCause | None
    impact: list[str]
    precedents: list[Precedent]
    occurrences: Occurrence | None
    incidents: list[IncidentRead]
    trace_id: str | None
