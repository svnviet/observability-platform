import uuid
from datetime import datetime

from app.core.config import jaeger_url
from app.db.event_repository import EventRepository
from app.db.models import StepAttemptRow, WorkflowRunRow, WorkflowStepRow
from app.db.workflow_repository import WorkflowRepository
from app.schemas.enums import WorkflowStatus
from app.schemas.ops import RejectedEventRead
from app.schemas.workflows import (
    AttemptRead,
    EventRead,
    Page,
    StepRead,
    TimelineEntry,
    WorkflowRunDetail,
    WorkflowRunRead,
)


class WorkflowQueryService:
    def __init__(self, workflows: WorkflowRepository, events: EventRepository) -> None:
        self._workflows = workflows
        self._events = events

    def search(
        self,
        *,
        workflow_id: str | None,
        run_key: str | None,
        status: WorkflowStatus | None,
        service: str | None,
        started_after: datetime | None,
        started_before: datetime | None,
        limit: int,
        offset: int,
    ) -> Page[WorkflowRunRead]:
        rows, total = self._workflows.search_runs(
            workflow_id=workflow_id,
            run_key=run_key,
            status=status,
            service=service,
            started_after=started_after,
            started_before=started_before,
            limit=limit,
            offset=offset,
        )
        return Page(items=[_run(r) for r in rows], total=total, limit=limit, offset=offset)

    def detail(self, run_id: uuid.UUID) -> WorkflowRunDetail | None:
        run = self._workflows.get_run_with_steps(run_id)
        if run is None:
            return None
        return WorkflowRunDetail(**_run(run).model_dump(), steps=[_step(s) for s in run.steps])

    def steps(self, run_id: uuid.UUID) -> list[StepRead] | None:
        run = self._workflows.get_run_with_steps(run_id)
        return None if run is None else [_step(s) for s in run.steps]

    def timeline(self, run_id: uuid.UUID) -> list[TimelineEntry] | None:
        run = self._workflows.get_run_with_steps(run_id)
        if run is None:
            return None
        entries = [
            TimelineEntry(
                kind="workflow",
                name=run.definition.name if run.definition else run.workflow_id,
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
                duration_ms=run.duration_ms,
            )
        ]
        step_entries: list[TimelineEntry] = []
        for step in run.steps:
            service_name = step.service.name if step.service else None
            for attempt in step.attempts:
                step_entries.append(
                    TimelineEntry(
                        kind="step_attempt",
                        name=step.step_name,
                        step_id=step.id,
                        attempt_number=attempt.attempt_number,
                        status=attempt.status,
                        service_name=service_name,
                        worker_key=attempt.worker_key,
                        started_at=attempt.started_at,
                        finished_at=attempt.finished_at,
                        duration_ms=_duration(attempt.started_at, attempt.finished_at),
                    )
                )
            if not step.attempts:  # queued or skipped steps have no attempt row
                step_entries.append(
                    TimelineEntry(
                        kind="step_attempt",
                        name=step.step_name,
                        step_id=step.id,
                        status=step.status,
                        service_name=service_name,
                        started_at=step.started_at,
                        finished_at=step.finished_at,
                        duration_ms=_duration(step.started_at, step.finished_at),
                    )
                )
        # Stable sort: entries without a start time go last, keeping step/attempt order.
        step_entries.sort(
            key=lambda e: (e.started_at is None, e.started_at.timestamp() if e.started_at else 0.0)
        )
        return entries + step_entries

    def events(self, run_id: uuid.UUID, limit: int, offset: int) -> Page[EventRead] | None:
        if self._workflows.get_run(run_id) is None:
            return None
        rows, total = self._events.list_for_run(run_id, limit, offset)
        return Page(
            items=[EventRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
        )

    def rejected(self, limit: int, offset: int) -> Page[RejectedEventRead]:
        rows, total = self._events.list_rejected(limit, offset)
        return Page(
            items=[RejectedEventRead.model_validate(r, from_attributes=True) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def event(self, event_id: str) -> EventRead | None:
        row = self._events.get_by_event_id(event_id)
        return None if row is None else EventRead.model_validate(row)


def trace_url(trace_id: str | None) -> str | None:
    base = jaeger_url()
    return f"{base.rstrip('/')}/trace/{trace_id}" if base and trace_id else None


def _duration(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _run(run: WorkflowRunRow) -> WorkflowRunRead:
    return WorkflowRunRead(
        id=run.id,
        run_key=run.run_key,
        workflow_id=run.workflow_id,
        workflow_name=run.definition.name if run.definition else None,
        status=run.status,
        correlation_id=run.correlation_id,
        trace_id=run.trace_id,
        trace_url=trace_url(run.trace_id),
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        last_event_at=run.last_event_at,
        input_metadata=run.input_metadata,
        output_metadata=run.output_metadata,
        error_details=run.error_details,
    )


def _attempt(a: StepAttemptRow) -> AttemptRead:
    return AttemptRead.model_validate(a).model_copy(update={"trace_url": trace_url(a.trace_id)})


def _step(s: WorkflowStepRow) -> StepRead:
    return StepRead(
        id=s.id,
        step_key=s.step_key,
        step_name=s.step_name,
        parent_step_id=s.parent_step_id,
        service_name=s.service.name if s.service else None,
        status=s.status,
        latest_attempt_number=s.latest_attempt_number,
        sequence_number=s.sequence_number,
        started_at=s.started_at,
        finished_at=s.finished_at,
        attempts=[_attempt(a) for a in s.attempts],
    )
