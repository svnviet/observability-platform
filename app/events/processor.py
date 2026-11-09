from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.incident_repository import IncidentRepository
from app.db.models import StepAttemptRow, WorkflowRunRow, WorkflowStepRow
from app.db.workflow_repository import WorkflowRepository
from app.events.state_machine import (
    STEP_TARGET,
    STEP_TERMINAL,
    WORKFLOW_TARGET,
    WORKFLOW_TERMINAL,
    TransitionPolicy,
)
from app.schemas.enums import AttemptStatus, Disposition, EventType, Severity, StepStatus, WorkflowStatus
from app.schemas.events import STEP_EVENT_TYPES, EventIn

_FAILED_WORKFLOW = frozenset({WorkflowStatus.FAILED, WorkflowStatus.TIMED_OUT})


def failure_incident_key(run_id) -> str:
    return f"workflow-failed:{run_id}"


@dataclass
class ApplyResult:
    disposition: Disposition
    reason: str | None = None
    step: WorkflowStepRow | None = None
    attempt: StepAttemptRow | None = None


class EventProcessor:
    """Applies one event to the materialized run/step/attempt state.

    The caller owns the transaction and must hold the run's row lock.
    """

    def __init__(self, workflows: WorkflowRepository, incidents: IncidentRepository) -> None:
        self._workflows = workflows
        self._incidents = incidents

    def apply(self, event: EventIn, run: WorkflowRunRow) -> ApplyResult:
        if event.event_type in STEP_EVENT_TYPES:
            return self._apply_step(event, run)
        return self._apply_workflow(event, run)

    def _apply_workflow(self, event: EventIn, run: WorkflowRunRow) -> ApplyResult:
        target = WORKFLOW_TARGET[event.event_type]
        disposition, reason = TransitionPolicy.workflow(WorkflowStatus(run.status), target)
        if disposition is Disposition.QUARANTINED:
            return ApplyResult(disposition, reason)

        self._enrich_run(event, run)
        if event.event_type is EventType.WORKFLOW_STARTED:
            run.started_at = _earliest(run.started_at, event.occurred_at)
        run.last_event_at = _latest(run.last_event_at, event.occurred_at)

        if disposition is Disposition.APPLIED:
            run.status = target.value
            if target in WORKFLOW_TERMINAL:
                run.finished_at = event.occurred_at
                if event.data.output_metadata is not None:
                    run.output_metadata = event.data.output_metadata
                if event.data.error is not None:
                    run.error_details = event.data.error
                if target in _FAILED_WORKFLOW:
                    self._open_failure_incident(event, run)
        _recompute_duration(run)
        return ApplyResult(disposition, reason)

    def _open_failure_incident(self, event: EventIn, run: WorkflowRunRow) -> None:
        service = self._workflows.upsert_service(
            event.source.service_name, event.source.environment, event.source.service_version
        )
        error = event.data.error or {}
        name = event.data.workflow_name or (run.definition.name if run.definition else run.workflow_id)
        self._incidents.open_incident(
            dedupe_key=failure_incident_key(run.id),
            severity=Severity.MEDIUM,
            title=f"Workflow {name} {event.event_type.value[9:].lower()}",
            description=error.get("message"),
            service_id=service.id,
            workflow_run_id=run.id,
            now=datetime.now(UTC),
        )

    def reconcile_failure_incident(self, run: WorkflowRunRow) -> None:
        """After a replay: a run that is no longer failed should not keep its failure incident open."""
        if WorkflowStatus(run.status) not in _FAILED_WORKFLOW:
            self._incidents.resolve_by_key(failure_incident_key(run.id), datetime.now(UTC))

    def _enrich_run(self, event: EventIn, run: WorkflowRunRow) -> None:
        ctx, data = event.context, event.data
        run.correlation_id = run.correlation_id or ctx.correlation_id
        run.trace_id = run.trace_id or ctx.trace_id
        if data.input_metadata is not None:
            run.input_metadata = {**run.input_metadata, **data.input_metadata}
        if data.workflow_name and run.workflow_definition_id is None:
            definition = self._workflows.upsert_definition(data.workflow_name, data.workflow_version or "1")
            run.workflow_definition_id = definition.id

    def _apply_step(self, event: EventIn, run: WorkflowRunRow) -> ApplyResult:
        ctx, data = event.context, event.data
        assert ctx.step_id is not None  # guaranteed by EventIn validation for step events
        step = self._workflows.get_or_create_step(
            run, ctx.step_id, data.step_name or ctx.step_id, data.sequence_number
        )
        target = STEP_TARGET[event.event_type]
        if event.event_type is EventType.STEP_FAILED and data.will_retry:
            target = StepStatus.RETRYING

        disposition, reason = TransitionPolicy.step(
            StepStatus(step.status), step.latest_attempt_number, data.attempt_number, target
        )
        if disposition is Disposition.QUARANTINED:
            return ApplyResult(disposition, reason, step=step)

        self._enrich_step(event, run, step)
        attempt = self._record_attempt(event, step)
        if event.event_type is EventType.STEP_STARTED:
            step.started_at = _earliest(step.started_at, event.occurred_at)
        run.last_event_at = _latest(run.last_event_at, event.occurred_at)

        if disposition is Disposition.APPLIED:
            step.status = target.value
            step.latest_attempt_number = data.attempt_number
            step.finished_at = event.occurred_at if target in STEP_TERMINAL else None
        return ApplyResult(disposition, reason, step=step, attempt=attempt)

    def _enrich_step(self, event: EventIn, run: WorkflowRunRow, step: WorkflowStepRow) -> None:
        if step.service_id is None:
            src = event.source
            step.service_id = self._workflows.upsert_service(
                src.service_name, src.environment, src.service_version
            ).id
        parent_key = event.data.parent_step_id
        if parent_key and step.parent_step_id is None:
            parent = self._workflows.find_step_by_key(run, parent_key)
            if parent is not None:
                step.parent_step_id = parent.id

    def _record_attempt(self, event: EventIn, step: WorkflowStepRow) -> StepAttemptRow | None:
        """Attempt rows are history: always updated, regardless of the step-level outcome."""
        etype = event.event_type
        if etype not in (
            EventType.STEP_STARTED,
            EventType.STEP_COMPLETED,
            EventType.STEP_FAILED,
            EventType.STEP_CANCELLED,
        ):
            return None
        attempt = self._workflows.get_or_create_attempt(step, event.data.attempt_number)
        attempt.attempt_key = attempt.attempt_key or event.context.step_attempt_id
        attempt.worker_key = attempt.worker_key or event.source.worker_id
        attempt.trace_id = attempt.trace_id or event.context.trace_id

        if etype is EventType.STEP_STARTED:
            attempt.started_at = _earliest(attempt.started_at, event.occurred_at)
        elif attempt.status == AttemptStatus.RUNNING.value:  # first terminal event wins
            attempt.status = {
                EventType.STEP_COMPLETED: AttemptStatus.COMPLETED,
                EventType.STEP_FAILED: AttemptStatus.FAILED,
                EventType.STEP_CANCELLED: AttemptStatus.CANCELLED,
            }[etype].value
            attempt.finished_at = event.occurred_at
            if event.data.error is not None:
                attempt.error_details = event.data.error
        return attempt


def _earliest(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None or candidate < current else current


def _latest(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None or candidate > current else current


def _recompute_duration(run: WorkflowRunRow) -> None:
    if run.started_at and run.finished_at:
        run.duration_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
