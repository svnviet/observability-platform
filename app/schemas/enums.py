from enum import StrEnum


class WorkflowStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class AttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventType(StrEnum):
    WORKFLOW_CREATED = "WORKFLOW_CREATED"
    WORKFLOW_QUEUED = "WORKFLOW_QUEUED"
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    WORKFLOW_CANCELLED = "WORKFLOW_CANCELLED"
    WORKFLOW_TIMED_OUT = "WORKFLOW_TIMED_OUT"
    STEP_QUEUED = "STEP_QUEUED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    STEP_SKIPPED = "STEP_SKIPPED"
    STEP_CANCELLED = "STEP_CANCELLED"


class Disposition(StrEnum):
    """What the processor did with a stored event."""

    APPLIED = "APPLIED"  # advanced the materialized state
    STALE = "STALE"  # valid but superseded or a no-op (late, duplicate-in-effect)
    QUARANTINED = "QUARANTINED"  # contradicts current state; kept for review/replay


class IngestOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"


class InstanceStatus(StrEnum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    STOPPED = "STOPPED"


class WorkerStatus(StrEnum):
    REGISTERED = "REGISTERED"
    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"
    UNHEALTHY = "UNHEALTHY"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
