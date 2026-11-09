import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.event_repository import EventRepository
from app.db.workflow_repository import WorkflowRepository
from app.events.processor import EventProcessor
from app.schemas.enums import Disposition
from app.schemas.events import EventIn
from app.schemas.workflows import ReplayRunResult


class EventReplayService:
    """Rebuild a run's materialized state from its immutable event log.

    Events are re-applied in occurrence order, so the result no longer depends on the order
    they happened to arrive in (e.g. which of two conflicting terminal events came first).
    """

    def __init__(
        self,
        session: Session,
        events: EventRepository,
        workflows: WorkflowRepository,
        processor: EventProcessor,
    ) -> None:
        self._session = session
        self._events = events
        self._workflows = workflows
        self._processor = processor

    def replay_runs(self, run_ids: list[uuid.UUID]) -> list[ReplayRunResult]:
        return [self._replay_one(run_id) for run_id in run_ids]

    def _replay_one(self, run_id: uuid.UUID) -> ReplayRunResult:
        run = self._workflows.get_run(run_id)
        if run is None:
            return ReplayRunResult(workflow_run_id=run_id, found=False)
        run = self._workflows.get_or_create_run_locked(run.run_key, run.workflow_id)

        rows = self._events.all_for_run_ordered(run.id)
        for row in rows:  # release FKs before the derived rows are dropped
            row.workflow_step_id = None
            row.attempt_id = None
        self._session.flush()
        self._workflows.reset_projection(run)

        counts = {d: 0 for d in Disposition}
        for row in rows:
            try:
                event = EventIn.model_validate(row.payload)
            except ValidationError:
                row.disposition = Disposition.QUARANTINED.value
                row.disposition_reason = "stored payload no longer validates"
                counts[Disposition.QUARANTINED] += 1
                continue
            applied = self._processor.apply(event, run)
            row.workflow_step_id = applied.step.id if applied.step else None
            row.attempt_id = applied.attempt.id if applied.attempt else None
            row.disposition = applied.disposition.value
            row.disposition_reason = applied.reason
            counts[applied.disposition] += 1
        self._processor.reconcile_failure_incident(run)
        self._session.commit()
        return ReplayRunResult(
            workflow_run_id=run_id,
            found=True,
            events_replayed=len(rows),
            applied=counts[Disposition.APPLIED],
            stale=counts[Disposition.STALE],
            quarantined=counts[Disposition.QUARANTINED],
        )
